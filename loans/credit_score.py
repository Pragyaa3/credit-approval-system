from datetime import date
from .models import Loan


def calculate_monthly_installment(principal: float, annual_rate: float, tenure_months: int) -> float:
    """
    Calculate EMI using compound interest (reducing balance method).
    Formula: EMI = P * r * (1+r)^n / ((1+r)^n - 1)
    where r = monthly interest rate, n = tenure in months
    """
    if annual_rate == 0:
        return round(principal / tenure_months, 2)

    monthly_rate = annual_rate / (12 * 100)
    factor = (1 + monthly_rate) ** tenure_months
    emi = principal * monthly_rate * factor / (factor - 1)
    return round(emi, 2)


def calculate_credit_score(customer) -> int:
    """
    Calculate credit score (0-100) based on historical loan data.

    Components:
      1. Past loans paid on time
      2. Number of loans taken
      3. Loan activity in the current year
      4. Loan approved volume vs approved limit
      5. Override: score = 0 if current loans exceed approved limit
    """
    loans = Loan.objects.filter(customer=customer)

    if not loans.exists():
        # No history — assign a moderate score
        return 50

    # --- Component 5: Hard override ---
    total_current_loan_amount = sum(
        loan.loan_amount for loan in loans if _is_active_loan(loan)
    )
    if total_current_loan_amount > customer.approved_limit:
        return 0

    total_loans = loans.count()
    score = 0

    # --- Component 1: EMI paid on time (0-30 points) ---
    total_emis = sum(loan.tenure for loan in loans)
    total_paid_on_time = sum(loan.emis_paid_on_time for loan in loans)
    if total_emis > 0:
        on_time_ratio = total_paid_on_time / total_emis
        score += int(on_time_ratio * 30)

    # --- Component 2: Number of loans taken (0-20 points) ---
    # Fewer loans = higher score (up to 5 loans is ideal; more penalises slightly)
    if total_loans == 0:
        score += 20
    elif total_loans <= 2:
        score += 20
    elif total_loans <= 5:
        score += 15
    elif total_loans <= 10:
        score += 10
    else:
        score += 5

    # --- Component 3: Loan activity in current year (0-20 points) ---
    current_year = date.today().year
    loans_this_year = sum(
        1 for loan in loans
        if loan.start_date and loan.start_date.year == current_year
    )
    if loans_this_year == 0:
        score += 20
    elif loans_this_year <= 2:
        score += 15
    elif loans_this_year <= 4:
        score += 10
    else:
        score += 5

    # --- Component 4: Loan approved volume vs approved limit (0-30 points) ---
    total_approved_volume = sum(loan.loan_amount for loan in loans)
    if customer.approved_limit > 0:
        volume_ratio = total_approved_volume / customer.approved_limit
        if volume_ratio <= 0.3:
            score += 30
        elif volume_ratio <= 0.5:
            score += 25
        elif volume_ratio <= 0.75:
            score += 15
        elif volume_ratio <= 1.0:
            score += 10
        else:
            score += 0

    return min(score, 100)


def get_eligibility(customer, loan_amount: float, interest_rate: float, tenure: int) -> dict:
    """
    Determine loan eligibility based on credit score and EMI constraints.

    Returns a dict with:
      - approved (bool)
      - corrected_interest_rate (float)
      - monthly_installment (float)
    """
    credit_score = calculate_credit_score(customer)

    # Check if total current EMIs exceed 50% of monthly salary
    active_loans = Loan.objects.filter(customer=customer)
    current_emi_total = sum(
        loan.monthly_repayment for loan in active_loans if _is_active_loan(loan)
    )

    emi_cap = customer.monthly_salary * 0.5

    # Determine minimum interest rate required based on credit score
    if credit_score > 50:
        min_required_rate = 0        # Any rate is fine
    elif 30 < credit_score <= 50:
        min_required_rate = 12.0
    elif 10 < credit_score <= 30:
        min_required_rate = 16.0
    else:
        # Score <= 10: reject outright
        emi = calculate_monthly_installment(loan_amount, interest_rate, tenure)
        return {
            'approved': False,
            'corrected_interest_rate': interest_rate,
            'monthly_installment': emi,
            'credit_score': credit_score,
        }

    # Correct interest rate if below the required slab
    corrected_rate = interest_rate if interest_rate >= min_required_rate else min_required_rate

    # Calculate EMI using the corrected rate
    emi = calculate_monthly_installment(loan_amount, corrected_rate, tenure)

    # Reject if adding this EMI would exceed 50% of salary
    if current_emi_total + emi > emi_cap:
        return {
            'approved': False,
            'corrected_interest_rate': corrected_rate,
            'monthly_installment': emi,
            'credit_score': credit_score,
        }

    return {
        'approved': True,
        'corrected_interest_rate': corrected_rate,
        'monthly_installment': emi,
        'credit_score': credit_score,
    }


def _is_active_loan(loan) -> bool:
    """A loan is considered active if its end date is in the future or not set."""
    if loan.end_date is None:
        return True
    return loan.end_date >= date.today()