from apps.authentication.models import CreditTransaction


def create_credit_transaction(user, delta, description, source_type='', source_id='', metadata=None):
    return CreditTransaction.objects.create(
        user=user,
        entry_type=CreditTransaction.TYPE_CREDIT if delta >= 0 else CreditTransaction.TYPE_DEBIT,
        delta=delta,
        balance_after=user.ai_credits,
        description=description[:255],
        source_type=source_type or '',
        source_id=str(source_id or ''),
        metadata=metadata or {},
    )
