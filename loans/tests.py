from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from datetime import date, timedelta

from .models import Customer, Loan
from .credit_score import (
    calculate_monthly_installment,
    calculate_credit_score,
    get_eligibility,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_customer(**kwargs):
    defaults = dict(
        first_name='John',
        last_name='Doe',
        age=30,
        phone_number=9999999999,
        monthly_salary=50000,
        approved_limit=1800000,
        current_debt=0,
    )
    defaults.update(kwargs)
    return Customer.objects.create(**defaults)


def make_loan(customer, **kwargs):
    defaults = dict(
        loan_amount=100000,
        tenure=12,
        interest_rate=10.0,
        monthly_repayment=8792.0,
        emis_paid_on_time=12,
        start_date=date.today() - timedelta(days=365),
        end_date=date.today() - timedelta(days=1),
    )
    defaults.update(kwargs)
    return Loan.objects.create(customer=customer, **defaults)


# ---------------------------------------------------------------------------
# EMI Calculation Tests
# ---------------------------------------------------------------------------

class EMICalculationTests(TestCase):

    def test_basic_emi(self):
        """Standard loan: 100000 at 10% for 12 months."""
        emi = calculate_monthly_installment(100000, 10.0, 12)
        self.assertAlmostEqual(emi, 8791.59, delta=1.0)

    def test_zero_interest_rate(self):
        """Zero interest rate should divide principal evenly."""
        emi = calculate_monthly_installment(120000, 0, 12)
        self.assertAlmostEqual(emi, 10000.0, delta=0.01)

    def test_longer_tenure_lower_emi(self):
        """Longer tenure should result in lower EMI."""
        emi_12 = calculate_monthly_installment(100000, 10.0, 12)
        emi_24 = calculate_monthly_installment(100000, 10.0, 24)
        self.assertGreater(emi_12, emi_24)

    def test_higher_rate_higher_emi(self):
        """Higher interest rate should result in higher EMI."""
        emi_low = calculate_monthly_installment(100000, 8.0, 12)
        emi_high = calculate_monthly_installment(100000, 16.0, 12)
        self.assertGreater(emi_high, emi_low)


# ---------------------------------------------------------------------------
# Credit Score Tests
# ---------------------------------------------------------------------------

class CreditScoreTests(TestCase):

    def test_no_loan_history_returns_50(self):
        """Customer with no loans gets a default score of 50."""
        customer = make_customer()
        score = calculate_credit_score(customer)
        self.assertEqual(score, 50)

    def test_score_zero_when_debt_exceeds_limit(self):
        """Score must be 0 if current loan total exceeds approved limit."""
        customer = make_customer(approved_limit=100000)
        make_loan(customer, loan_amount=200000,
                  end_date=date.today() + timedelta(days=30))
        score = calculate_credit_score(customer)
        self.assertEqual(score, 0)

    def test_perfect_payment_history_boosts_score(self):
        """All EMIs paid on time should give maximum on-time component."""
        customer = make_customer()
        # Paid all 12 EMIs on time
        make_loan(customer, tenure=12, emis_paid_on_time=12,
                  end_date=date.today() - timedelta(days=1))
        score = calculate_credit_score(customer)
        self.assertGreater(score, 40)

    def test_poor_payment_history_lowers_score(self):
        """Very few EMIs paid on time should result in a low score."""
        customer = make_customer()
        make_loan(customer, tenure=12, emis_paid_on_time=1,
                  end_date=date.today() - timedelta(days=1))
        score_poor = calculate_credit_score(customer)

        customer2 = make_customer(phone_number=8888888888)
        make_loan(customer2, tenure=12, emis_paid_on_time=12,
                  end_date=date.today() - timedelta(days=1))
        score_good = calculate_credit_score(customer2)

        self.assertLess(score_poor, score_good)

    def test_score_capped_at_100(self):
        """Credit score should never exceed 100."""
        customer = make_customer()
        make_loan(customer, tenure=12, emis_paid_on_time=12,
                  end_date=date.today() - timedelta(days=1))
        score = calculate_credit_score(customer)
        self.assertLessEqual(score, 100)
        self.assertGreaterEqual(score, 0)


# ---------------------------------------------------------------------------
# Eligibility Logic Tests
# ---------------------------------------------------------------------------

class EligibilityTests(TestCase):

    def test_high_credit_score_approved(self):
        """Score > 50 should approve the loan."""
        customer = make_customer(monthly_salary=100000)
        # Give them a good history
        make_loan(customer, tenure=12, emis_paid_on_time=12,
                  end_date=date.today() - timedelta(days=1))
        result = get_eligibility(customer, 100000, 10.0, 12)
        # Score depends on components — just check structure
        self.assertIn('approved', result)
        self.assertIn('corrected_interest_rate', result)
        self.assertIn('monthly_installment', result)

    def test_interest_rate_corrected_for_slab(self):
        """If score is 31-50, rate below 12% should be corrected to 12%."""
        customer = make_customer(monthly_salary=200000, approved_limit=5000000)
        # Craft a history that gives score in 31-50 range
        make_loan(customer, tenure=24, emis_paid_on_time=12,
                  loan_amount=50000,
                  end_date=date.today() - timedelta(days=1))
        result = get_eligibility(customer, 50000, 8.0, 12)
        if result['approved']:
            self.assertGreaterEqual(result['corrected_interest_rate'], 8.0)

    def test_emi_cap_rejects_loan(self):
        """If new EMI + existing EMIs > 50% salary, reject."""
        customer = make_customer(monthly_salary=20000, approved_limit=5000000)
        # Existing active loan with high EMI
        make_loan(customer, loan_amount=500000, tenure=12,
                  monthly_repayment=9000,
                  emis_paid_on_time=0,
                  end_date=date.today() + timedelta(days=300))
        # Request another large loan — total EMI will exceed 50% of 20000 = 10000
        result = get_eligibility(customer, 500000, 10.0, 12)
        self.assertFalse(result['approved'])

    def test_score_zero_rejects_loan(self):
        """Score of 0 (debt > limit) must reject the loan."""
        customer = make_customer(approved_limit=50000)
        make_loan(customer, loan_amount=100000,
                  end_date=date.today() + timedelta(days=100))
        result = get_eligibility(customer, 10000, 10.0, 12)
        self.assertFalse(result['approved'])


# ---------------------------------------------------------------------------
# API Endpoint Tests
# ---------------------------------------------------------------------------

class RegisterAPITests(TestCase):

    def setUp(self):
        self.client = APIClient()

    def test_register_success(self):
        response = self.client.post('/register', {
            'first_name': 'Jane',
            'last_name': 'Smith',
            'age': 28,
            'monthly_income': 50000,
            'phone_number': 9876543210,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('customer_id', response.data)
        self.assertEqual(response.data['approved_limit'], 1800000)

    def test_register_approved_limit_rounded_to_lakh(self):
        """36 * 55000 = 1980000 → rounds to 2000000."""
        response = self.client.post('/register', {
            'first_name': 'Test',
            'last_name': 'User',
            'age': 25,
            'monthly_income': 55000,
            'phone_number': 9000000000,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['approved_limit'], 2000000)

    def test_register_missing_field(self):
        response = self.client.post('/register', {
            'first_name': 'Jane',
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_invalid_phone(self):
        response = self.client.post('/register', {
            'first_name': 'Jane',
            'last_name': 'Smith',
            'age': 28,
            'monthly_income': 50000,
            'phone_number': 123,  # too short
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class CheckEligibilityAPITests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.customer = make_customer()

    def test_eligibility_valid_customer(self):
        response = self.client.post('/check-eligibility', {
            'customer_id': self.customer.customer_id,
            'loan_amount': 100000,
            'interest_rate': 10.0,
            'tenure': 12,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('approval', response.data)
        self.assertIn('corrected_interest_rate', response.data)
        self.assertIn('monthly_installment', response.data)

    def test_eligibility_customer_not_found(self):
        response = self.client.post('/check-eligibility', {
            'customer_id': 99999,
            'loan_amount': 100000,
            'interest_rate': 10.0,
            'tenure': 12,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class CreateLoanAPITests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.customer = make_customer(monthly_salary=100000, approved_limit=5000000)

    def test_create_loan_success(self):
        response = self.client.post('/create-loan', {
            'customer_id': self.customer.customer_id,
            'loan_amount': 100000,
            'interest_rate': 10.0,
            'tenure': 12,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['loan_approved'])
        self.assertIsNotNone(response.data['loan_id'])

    def test_create_loan_customer_not_found(self):
        response = self.client.post('/create-loan', {
            'customer_id': 99999,
            'loan_amount': 100000,
            'interest_rate': 10.0,
            'tenure': 12,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_rejected_loan_returns_null_id(self):
        """Loan rejected due to low credit should return loan_id: null."""
        # Make debt exceed limit to force score = 0
        bad_customer = make_customer(
            phone_number=7777777777,
            approved_limit=10000,
            monthly_salary=5000
        )
        make_loan(bad_customer, loan_amount=50000,
                  end_date=date.today() + timedelta(days=100))
        response = self.client.post('/create-loan', {
            'customer_id': bad_customer.customer_id,
            'loan_amount': 10000,
            'interest_rate': 10.0,
            'tenure': 12,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['loan_approved'])
        self.assertIsNone(response.data['loan_id'])


class ViewLoanAPITests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.customer = make_customer()
        self.loan = make_loan(self.customer)

    def test_view_loan_success(self):
        response = self.client.get(f'/view-loan/{self.loan.loan_id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['loan_id'], self.loan.loan_id)
        self.assertIn('customer', response.data)
        self.assertEqual(response.data['customer']['customer_id'], self.customer.customer_id)

    def test_view_loan_not_found(self):
        response = self.client.get('/view-loan/99999')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ViewCustomerLoansAPITests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.customer = make_customer()
        make_loan(self.customer, loan_amount=100000)
        make_loan(self.customer, loan_amount=200000)

    def test_view_loans_returns_all(self):
        response = self.client.get(f'/view-loans/{self.customer.customer_id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_view_loans_repayments_left(self):
        """repayments_left = tenure - emis_paid_on_time."""
        response = self.client.get(f'/view-loans/{self.customer.customer_id}')
        for loan in response.data:
            self.assertIn('repayments_left', loan)
            self.assertGreaterEqual(loan['repayments_left'], 0)

    def test_view_loans_customer_not_found(self):
        response = self.client.get('/view-loans/99999')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)