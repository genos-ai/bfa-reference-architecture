"""add foreign key constraints to project context layer

Revision ID: 92813afeaf50
Revises: 1dc5c2cc9d93
Create Date: 2026-03-11 15:35:54.823314+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# Revision identifiers
revision: str = '92813afeaf50'
down_revision: Union[str, None] = '1dc5c2cc9d93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Apply migration."""
    op.create_foreign_key('fk_context_changes_context_id', 'context_changes', 'project_contexts', ['context_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_milestone_summaries_project_id', 'milestone_summaries', 'projects', ['project_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_mission_records_project_id', 'mission_records', 'projects', ['project_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_missions_project_id', 'missions', 'projects', ['project_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_playbook_runs_project_id', 'playbook_runs', 'projects', ['project_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_project_contexts_project_id', 'project_contexts', 'projects', ['project_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_project_decisions_project_id', 'project_decisions', 'projects', ['project_id'], ['id'], ondelete='CASCADE')
    op.create_unique_constraint('uq_project_members_project_user', 'project_members', ['project_id', 'user_id'])
    op.create_foreign_key('fk_project_members_project_id', 'project_members', 'projects', ['project_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    """Revert migration."""
    op.drop_constraint('fk_project_members_project_id', 'project_members', type_='foreignkey')
    op.drop_constraint('uq_project_members_project_user', 'project_members', type_='unique')
    op.drop_constraint('fk_project_decisions_project_id', 'project_decisions', type_='foreignkey')
    op.drop_constraint('fk_project_contexts_project_id', 'project_contexts', type_='foreignkey')
    op.drop_constraint('fk_playbook_runs_project_id', 'playbook_runs', type_='foreignkey')
    op.drop_constraint('fk_missions_project_id', 'missions', type_='foreignkey')
    op.drop_constraint('fk_mission_records_project_id', 'mission_records', type_='foreignkey')
    op.drop_constraint('fk_milestone_summaries_project_id', 'milestone_summaries', type_='foreignkey')
    op.drop_constraint('fk_context_changes_context_id', 'context_changes', type_='foreignkey')
