from rest_framework import serializers
from .models import Customer, Loan


class RegisterCustomerSerializer(serializers.Serializer):
    """Serializer for incoming /register request body."""
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    age = serializers.IntegerField()
    monthly_income = serializers.IntegerField(min_value=0)
    phone_number = serializers.IntegerField()

    def validate_phone_number(self, value):
        if len(str(value)) < 10:
            raise serializers.ValidationError("Phone number must be at least 10 digits.")
        return value


class CustomerResponseSerializer(serializers.ModelSerializer):
    """Serializer for Customer response — used in /register and /view-loan."""
    name = serializers.SerializerMethodField()
    monthly_income = serializers.IntegerField(source='monthly_salary')

    class Meta:
        model = Customer
        fields = ['customer_id', 'name', 'age', 'monthly_income', 'approved_limit', 'phone_number']

    def get_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"


class CustomerBriefSerializer(serializers.ModelSerializer):
    """Brief customer info used inside /view-loan response."""
    class Meta:
        model = Customer
        fields = ['customer_id', 'first_name', 'last_name', 'phone_number', 'age']


class CheckEligibilityRequestSerializer(serializers.Serializer):
    """Serializer for incoming /check-eligibility request body."""
    customer_id = serializers.IntegerField()
    loan_amount = serializers.FloatField(min_value=0)
    interest_rate = serializers.FloatField(min_value=0)
    tenure = serializers.IntegerField(min_value=1)


class CreateLoanRequestSerializer(serializers.Serializer):
    """Serializer for incoming /create-loan request body."""
    customer_id = serializers.IntegerField()
    loan_amount = serializers.FloatField(min_value=0)
    interest_rate = serializers.FloatField(min_value=0)
    tenure = serializers.IntegerField(min_value=1)


class LoanDetailSerializer(serializers.ModelSerializer):
    """Full loan detail — used in /view-loan."""
    customer = CustomerBriefSerializer(read_only=True)

    class Meta:
        model = Loan
        fields = ['loan_id', 'customer', 'loan_amount', 'interest_rate', 'monthly_repayment', 'tenure']


class LoanListSerializer(serializers.ModelSerializer):
    """Loan summary per customer — used in /view-loans."""
    monthly_installment = serializers.FloatField(source='monthly_repayment')
    repayments_left = serializers.SerializerMethodField()

    class Meta:
        model = Loan
        fields = ['loan_id', 'loan_amount', 'interest_rate', 'monthly_installment', 'repayments_left']

    def get_repayments_left(self, obj):
        return max(0, obj.tenure - obj.emis_paid_on_time)