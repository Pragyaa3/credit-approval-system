# Credit Approval System

A REST API backend built with Django 4+, Django REST Framework, and PostgreSQL.
The system manages customer registration, evaluates loan eligibility based on credit scores,
and handles loan creation and retrieval.

---

## Tech Stack

- Python 3.11
- Django 4.2 + Django REST Framework
- PostgreSQL 15
- Docker + Docker Compose
- openpyxl (Excel ingestion)

---

## Project Structure

```
credit_system/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── manage.py
├── data/                            # Place your .xlsx files here
│   ├── customer_data.xlsx
│   └── loan_data.xlsx
├── credit_system/
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
└── loans/
    ├── models.py                    # Customer and Loan models
    ├── serializers.py               # Request/response serializers
    ├── views.py                     # All 5 API endpoints
    ├── urls.py                      # URL routing
    ├── credit_score.py              # Credit scoring and eligibility logic
    ├── tests.py                     # Unit tests
    ├── migrations/
    │   └── 0001_initial.py
    └── management/commands/
        └── ingest_data.py           # Background data ingestion command
```

---

## Getting Started

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop) installed and running

### Setup

1. Clone the repository
   ```bash
   git clone https://github.com/YOUR_USERNAME/credit-approval-system.git
   cd credit-approval-system
   ```

2. Add the Excel data files into the `data/` folder
   ```
   data/customer_data.xlsx
   data/loan_data.xlsx
   ```

3. Run the application
   ```bash
   docker compose up --build
   ```

That's it. Docker will:
- Start a PostgreSQL database
- Run all migrations
- Ingest data from both Excel files automatically
- Start the Django server at `http://localhost:8000`

---

## API Endpoints

### POST `/register`
Register a new customer. Approved limit is calculated as `36 × monthly_salary` rounded to the nearest lakh.

**Request**
```json
{
  "first_name": "John",
  "last_name": "Doe",
  "age": 30,
  "monthly_income": 50000,
  "phone_number": 9999999999
}
```

**Response**
```json
{
  "customer_id": 1,
  "name": "John Doe",
  "age": 30,
  "monthly_income": 50000,
  "approved_limit": 1800000,
  "phone_number": 9999999999
}
```

---

### POST `/check-eligibility`
Check loan eligibility based on the customer's credit score (0–100).

Credit score components:
- Past loans paid on time
- Number of loans taken
- Loan activity in the current year
- Loan approved volume vs approved limit

Approval slabs:

| Credit Score | Decision |
|---|---|
| > 50 | Approved at any interest rate |
| 31 – 50 | Approved only if interest rate ≥ 12% |
| 11 – 30 | Approved only if interest rate ≥ 16% |
| ≤ 10 | Rejected |
| Any + EMIs > 50% salary | Rejected |

**Request**
```json
{
  "customer_id": 1,
  "loan_amount": 100000,
  "interest_rate": 8.0,
  "tenure": 12
}
```

**Response**
```json
{
  "customer_id": 1,
  "approval": true,
  "interest_rate": 8.0,
  "corrected_interest_rate": 12.0,
  "tenure": 12,
  "monthly_installment": 8884.88
}
```

---

### POST `/create-loan`
Process and create a loan if the customer is eligible.

**Request**
```json
{
  "customer_id": 1,
  "loan_amount": 100000,
  "interest_rate": 14.0,
  "tenure": 12
}
```

**Response (approved)**
```json
{
  "loan_id": 101,
  "customer_id": 1,
  "loan_approved": true,
  "message": "Loan approved successfully.",
  "monthly_installment": 8978.62
}
```

**Response (rejected)**
```json
{
  "loan_id": null,
  "customer_id": 1,
  "loan_approved": false,
  "message": "Loan rejected: credit score is too low.",
  "monthly_installment": 8978.62
}
```

---

### GET `/view-loan/<loan_id>`
View details of a specific loan with customer information.

**Response**
```json
{
  "loan_id": 101,
  "customer": {
    "customer_id": 1,
    "first_name": "John",
    "last_name": "Doe",
    "phone_number": 9999999999,
    "age": 30
  },
  "loan_amount": 100000,
  "interest_rate": 14.0,
  "monthly_installment": 8978.62,
  "tenure": 12
}
```

---

### GET `/view-loans/<customer_id>`
View all loans for a specific customer.

**Response**
```json
[
  {
    "loan_id": 101,
    "loan_amount": 100000,
    "interest_rate": 14.0,
    "monthly_installment": 8978.62,
    "repayments_left": 10
  }
]
```

---

## Running Tests

```bash
docker compose run web python manage.py test
```

Expected output:
```
Found 20 test(s).
....................
----------------------------------------------------------------------
Ran 20 tests in 0.342s

OK
```

---

## EMI Calculation

Monthly installment is calculated using the compound interest (reducing balance) formula:

```
EMI = P × r × (1 + r)^n / ((1 + r)^n - 1)

where:
  P = principal loan amount
  r = monthly interest rate (annual rate / 12 / 100)
  n = tenure in months
```

---

## Notes

- The `data/` folder is listed in `.gitignore` — Excel files are not committed to the repo.
- On first startup, data is automatically ingested from the Excel files via a Django management command.
- If the database already has data, ingestion is skipped to avoid duplicates.