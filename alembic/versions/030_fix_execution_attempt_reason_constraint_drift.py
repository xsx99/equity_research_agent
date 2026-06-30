"""Repair execution attempt reason-code constraint drift.

Revision ID: 030
Revises: 029
Create Date: 2026-06-30

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CURRENT_REASON_CODE_CONSTRAINT = (
    "reason_code IN ("
    "'submitted', 'not_executable_action', 'instrument_mismatch', 'not_authorized', "
    "'risk_missing', 'risk_rejected', 'dry_run', 'broker_unavailable', "
    "'order_rejected', 'no_fill', 'missing_credentials', 'broker_error', "
    "'no_action_required'"
    ")"
)

_PREVIOUS_REASON_CODE_CONSTRAINT = (
    "reason_code IN ("
    "'submitted', 'not_executable_action', 'instrument_mismatch', 'not_authorized', "
    "'risk_missing', 'risk_rejected', 'dry_run', 'broker_unavailable', "
    "'order_rejected', 'no_fill', 'missing_credentials', 'broker_error'"
    ")"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_execution_attempts_reason_code",
        "execution_attempts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_execution_attempts_reason_code",
        "execution_attempts",
        _CURRENT_REASON_CODE_CONSTRAINT,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_execution_attempts_reason_code",
        "execution_attempts",
        type_="check",
    )
    op.create_check_constraint(
        "ck_execution_attempts_reason_code",
        "execution_attempts",
        _PREVIOUS_REASON_CODE_CONSTRAINT,
    )
