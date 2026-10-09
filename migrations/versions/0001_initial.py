"""Начальная схема."""

from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Зафиксированная начальная схема.
    op.create_table('app_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('allowed_chat_id', sa.BigInteger(), nullable=False),
    sa.Column('configured_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint('id = 1', name='settings_singleton'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('athletes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('display_name', sa.String(length=100), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key')
    )
    op.create_table('pending_actions',
    sa.Column('token', sa.String(length=32), nullable=False),
    sa.Column('chat_id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('kind', sa.String(length=32), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('expires_at', sa.DateTime(), nullable=False),
    sa.Column('used', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('token')
    )
    op.create_table('processed_messages',
    sa.Column('chat_id', sa.BigInteger(), nullable=False),
    sa.Column('message_id', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('chat_id', 'message_id')
    )
    op.create_table('programs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('schema_version', sa.Integer(), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint('version > 0 AND schema_version = 1', name='program_versions_valid'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key', 'version', name='program_version_unique')
    )
    with op.batch_alter_table('programs', schema=None) as batch_op:
        batch_op.create_index('one_active_program', ['active'], unique=True, sqlite_where=sa.text('active = 1'))

    op.create_table('program_days',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('program_id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('order', sa.Integer(), nullable=False),
    sa.CheckConstraint('"order" > 0', name='day_order_positive'),
    sa.ForeignKeyConstraint(['program_id'], ['programs.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('program_id', 'key'),
    sa.UniqueConstraint('program_id', 'order')
    )
    op.create_table('telegram_bindings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('telegram_user_id', sa.BigInteger(), nullable=False),
    sa.Column('athlete_id', sa.Integer(), nullable=False),
    sa.Column('telegram_username', sa.String(length=100), nullable=True),
    sa.Column('telegram_first_name', sa.String(length=100), nullable=True),
    sa.Column('bound_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['athlete_id'], ['athletes.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('athlete_id'),
    sa.UniqueConstraint('telegram_user_id')
    )
    op.create_table('program_exercises',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('program_day_id', sa.Integer(), nullable=False),
    sa.Column('exercise_key', sa.String(length=64), nullable=False),
    sa.Column('exercise_name', sa.String(length=100), nullable=False),
    sa.Column('order', sa.Integer(), nullable=False),
    sa.CheckConstraint('"order" > 0', name='exercise_order_positive'),
    sa.ForeignKeyConstraint(['program_day_id'], ['program_days.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('program_day_id', 'exercise_key'),
    sa.UniqueConstraint('program_day_id', 'order')
    )
    op.create_table('training_sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('chat_id', sa.BigInteger(), nullable=False),
    sa.Column('program_id', sa.Integer(), nullable=False),
    sa.Column('program_day_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('current_exercise_order', sa.Integer(), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.Column('started_at', sa.DateTime(), nullable=False),
    sa.Column('finished_at', sa.DateTime(), nullable=True),
    sa.Column('started_by_athlete_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("status IN ('active', 'completed', 'aborted')", name='session_status_valid'),
    sa.ForeignKeyConstraint(['program_day_id'], ['program_days.id'], ),
    sa.ForeignKeyConstraint(['program_id'], ['programs.id'], ),
    sa.ForeignKeyConstraint(['started_by_athlete_id'], ['athletes.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('training_sessions', schema=None) as batch_op:
        batch_op.create_index('one_active_session_per_chat', ['chat_id'], unique=True, sqlite_where=sa.text("status = 'active'"))

    op.create_table('prescribed_sets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('program_exercise_id', sa.Integer(), nullable=False),
    sa.Column('athlete_id', sa.Integer(), nullable=False),
    sa.Column('set_number', sa.Integer(), nullable=False),
    sa.Column('reps_min', sa.Integer(), nullable=False),
    sa.Column('reps_max', sa.Integer(), nullable=False),
    sa.Column('target_rir', sa.Integer(), nullable=True),
    sa.CheckConstraint('set_number > 0 AND reps_min > 0 AND reps_max >= reps_min AND reps_max <= 1000', name='prescription_positive'),
    sa.CheckConstraint('target_rir IS NULL OR target_rir BETWEEN 0 AND 10', name='rir_valid'),
    sa.ForeignKeyConstraint(['athlete_id'], ['athletes.id'], ),
    sa.ForeignKeyConstraint(['program_exercise_id'], ['program_exercises.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('program_exercise_id', 'athlete_id', 'set_number')
    )
    op.create_table('session_participants',
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('athlete_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['athlete_id'], ['athletes.id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['training_sessions.id'], ),
    sa.PrimaryKeyConstraint('session_id', 'athlete_id')
    )
    op.create_table('set_results',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('training_session_id', sa.Integer(), nullable=False),
    sa.Column('program_exercise_id', sa.Integer(), nullable=False),
    sa.Column('athlete_id', sa.Integer(), nullable=False),
    sa.Column('planned_set_number', sa.Integer(), nullable=True),
    sa.Column('reps', sa.Integer(), nullable=False),
    sa.Column('weight_kg', sa.Text(), nullable=False),
    sa.Column('subjective_rating', sa.String(length=16), nullable=True),
    sa.Column('telegram_chat_id', sa.BigInteger(), nullable=False),
    sa.Column('telegram_message_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(), nullable=True),
    sa.CheckConstraint("subjective_rating IS NULL OR subjective_rating IN ('easy', 'normal', 'hard')", name='rating_valid'),
    sa.CheckConstraint('reps BETWEEN 1 AND 1000', name='result_reps_valid'),
    sa.ForeignKeyConstraint(['athlete_id'], ['athletes.id'], ),
    sa.ForeignKeyConstraint(['program_exercise_id'], ['program_exercises.id'], ),
    sa.ForeignKeyConstraint(['training_session_id'], ['training_sessions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('telegram_chat_id', 'telegram_message_id', name='result_message_unique')
    )
    with op.batch_alter_table('set_results', schema=None) as batch_op:
        batch_op.create_index('one_live_planned_result', ['training_session_id', 'program_exercise_id', 'athlete_id', 'planned_set_number'], unique=True, sqlite_where=sa.text('deleted_at IS NULL'))
        batch_op.create_index('result_history', ['athlete_id', 'program_exercise_id'], unique=False)

    op.create_table('skipped_exercises',
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('exercise_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['exercise_id'], ['program_exercises.id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['training_sessions.id'], ),
    sa.PrimaryKeyConstraint('session_id', 'exercise_id')
    )
    


def downgrade():
    # Зафиксированная начальная схема.
    op.drop_table('skipped_exercises')
    with op.batch_alter_table('set_results', schema=None) as batch_op:
        batch_op.drop_index('result_history')
        batch_op.drop_index('one_live_planned_result', sqlite_where=sa.text('deleted_at IS NULL'))

    op.drop_table('set_results')
    op.drop_table('session_participants')
    op.drop_table('prescribed_sets')
    with op.batch_alter_table('training_sessions', schema=None) as batch_op:
        batch_op.drop_index('one_active_session_per_chat', sqlite_where=sa.text("status = 'active'"))

    op.drop_table('training_sessions')
    op.drop_table('program_exercises')
    op.drop_table('telegram_bindings')
    op.drop_table('program_days')
    with op.batch_alter_table('programs', schema=None) as batch_op:
        batch_op.drop_index('one_active_program', sqlite_where=sa.text('active = 1'))

    op.drop_table('programs')
    op.drop_table('processed_messages')
    op.drop_table('pending_actions')
    op.drop_table('athletes')
    op.drop_table('app_settings')
    

