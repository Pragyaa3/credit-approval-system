from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404

from .models import Customer, Loan
from .serializers import (
    RegisterCustomerSerializer,
    CheckEligibilityRequestSerializer,
    CreateLoanRequestSerializer,
    LoanDetailSerializer,
    LoanListSerializer,
)
from .credit_score import get_eligibility


def round_to_nearest_lakh(amount: int) -> int:
    """Round amount to nearest lakh (100,000)."""
    lakh = 100_000
    return round(amount / lakh) * lakh


class RegisterCustomerView(APIView):
    """
    POST /register
    Register a new customer and calculate their approved credit limit.
    approved_limit = 36 * monthly_salary, rounded to nearest lakh.
    """

    def post(self, request):
        serializer = RegisterCustomerSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        approved_limit = round_to_nearest_lakh(36 * data['monthly_income'])

        customer = Customer.objects.create(
            first_name=data['first_name'],
            last_name=data['last_name'],
            age=data['age'],
            phone_number=data['phone_number'],
            monthly_salary=data['monthly_income'],
            approved_limit=approved_limit,
            current_debt=0,
        )

        return Response({
            'customer_id': customer.customer_id,
            'name': f"{customer.first_name} {customer.last_name}",
            'age': customer.age,
            'monthly_income': customer.monthly_salary,
            'approved_limit': customer.approved_limit,
            'phone_number': customer.phone_number,
        }, status=status.HTTP_201_CREATED)


class CheckEligibilityView(APIView):
    """
    POST /check-eligibility
    Check if a customer is eligible for a loan based on their credit score.
    Returns corrected interest rate if the requested rate is below the slab.
    """

    def post(self, request):
        serializer = CheckEligibilityRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        try:
            customer = Customer.objects.get(customer_id=data['customer_id'])
        except Customer.DoesNotExist:
            return Response(
                {'error': 'Customer not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        eligibility = get_eligibility(
            customer=customer,
            loan_amount=data['loan_amount'],
            interest_rate=data['interest_rate'],
            tenure=data['tenure'],
        )

        return Response({
            'customer_id': customer.customer_id,
            'approval': eligibility['approved'],
            'interest_rate': data['interest_rate'],
            'corrected_interest_rate': eligibility['corrected_interest_rate'],
            'tenure': data['tenure'],
            'monthly_installment': eligibility['monthly_installment'],
        }, status=status.HTTP_200_OK)


class CreateLoanView(APIView):
    """
    POST /create-loan
    Create a loan if the customer is eligible.
    Uses the same eligibility logic as /check-eligibility.
    """

    def post(self, request):
        serializer = CreateLoanRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data

        try:
            customer = Customer.objects.get(customer_id=data['customer_id'])
        except Customer.DoesNotExist:
            return Response(
                {'error': 'Customer not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        eligibility = get_eligibility(
            customer=customer,
            loan_amount=data['loan_amount'],
            interest_rate=data['interest_rate'],
            tenure=data['tenure'],
        )

        if not eligibility['approved']:
            credit_score = eligibility['credit_score']
            if credit_score <= 10:
                message = 'Loan rejected: credit score is too low.'
            else:
                message = 'Loan rejected: total EMIs would exceed 50% of monthly salary.'

            return Response({
                'loan_id': None,
                'customer_id': customer.customer_id,
                'loan_approved': False,
                'message': message,
                'monthly_installment': eligibility['monthly_installment'],
            }, status=status.HTTP_200_OK)

        loan = Loan.objects.create(
            customer=customer,
            loan_amount=data['loan_amount'],
            tenure=data['tenure'],
            interest_rate=eligibility['corrected_interest_rate'],
            monthly_repayment=eligibility['monthly_installment'],
            emis_paid_on_time=0,
        )

        return Response({
            'loan_id': loan.loan_id,
            'customer_id': customer.customer_id,
            'loan_approved': True,
            'message': 'Loan approved successfully.',
            'monthly_installment': loan.monthly_repayment,
        }, status=status.HTTP_201_CREATED)


class ViewLoanView(APIView):
    """
    GET /view-loan/<loan_id>
    View details of a specific loan along with customer info.
    """

    def get(self, request, loan_id):
        loan = get_object_or_404(Loan.objects.select_related('customer'), loan_id=loan_id)
        serializer = LoanDetailSerializer(loan)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ViewCustomerLoansView(APIView):
    """
    GET /view-loans/<customer_id>
    View all loans for a specific customer.
    """

    def get(self, request, customer_id):
        customer = get_object_or_404(Customer, customer_id=customer_id)
        loans = Loan.objects.filter(customer=customer)
        serializer = LoanListSerializer(loans, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)