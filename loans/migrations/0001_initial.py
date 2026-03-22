from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Customer',
            fields=[
                ('customer_id', models.AutoField(primary_key=True, serialize=False)),
                ('first_name', models.CharField(max_length=100)),
                ('last_name', models.CharField(max_length=100)),
                ('age', models.IntegerField(blank=True, null=True)),
                ('phone_number', models.BigIntegerField()),
                ('monthly_salary', models.IntegerField()),
                ('approved_limit', models.IntegerField()),
                ('current_debt', models.FloatField(default=0)),
            ],
        ),
        migrations.CreateModel(
            name='Loan',
            fields=[
                ('loan_id', models.AutoField(primary_key=True, serialize=False)),
                ('loan_amount', models.FloatField()),
                ('tenure', models.IntegerField(help_text='Tenure in months')),
                ('interest_rate', models.FloatField()),
                ('monthly_repayment', models.FloatField()),
                ('emis_paid_on_time', models.IntegerField(default=0)),
                ('start_date', models.DateField(blank=True, null=True)),
                ('end_date', models.DateField(blank=True, null=True)),
                ('customer', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='loans',
                    to='loans.customer'
                )),
            ],
        ),
    ]