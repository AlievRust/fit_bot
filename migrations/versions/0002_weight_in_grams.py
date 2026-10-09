"""Хранить вес в целых граммах с точным преобразованием старых результатов."""

from decimal import Decimal, InvalidOperation

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    converted = []
    for result_id, weight_kg in connection.execute(sa.text("SELECT id, weight_kg FROM set_results")):
        try:
            grams = Decimal(weight_kg) * 1000
            valid = grams.is_finite() and 1 <= grams <= 2000000 and grams == grams.to_integral_value()
        except (InvalidOperation, ValueError, TypeError):
            valid = False
        if not valid:
            raise RuntimeError(f"Вес результата id={result_id} нельзя точно представить целыми граммами.")
        converted.append({"result_id": result_id, "weight_g": int(grams)})

    # Сначала проверены все значения; ни float, ни SQL CAST для перевода не нужны.
    op.add_column("set_results", sa.Column("weight_g", sa.Integer(), nullable=True))
    if converted:
        connection.execute(sa.text("UPDATE set_results SET weight_g = :weight_g WHERE id = :result_id"), converted)
    with op.batch_alter_table("set_results") as batch:
        batch.drop_column("weight_kg")
        batch.alter_column("weight_g", existing_type=sa.Integer(), nullable=False)
        batch.create_check_constraint("result_weight_g_valid", "typeof(weight_g) = 'integer' AND weight_g BETWEEN 1 AND 2000000")


def downgrade():
    connection = op.get_bind()
    converted = [
        {"result_id": result_id, "weight_kg": format(Decimal(weight_g) / 1000, "f")}
        for result_id, weight_g in connection.execute(sa.text("SELECT id, weight_g FROM set_results"))
    ]
    op.add_column("set_results", sa.Column("weight_kg", sa.Text(), nullable=True))
    if converted:
        connection.execute(sa.text("UPDATE set_results SET weight_kg = :weight_kg WHERE id = :result_id"), converted)
    with op.batch_alter_table("set_results") as batch:
        batch.drop_constraint("result_weight_g_valid", type_="check")
        batch.drop_column("weight_g")
        batch.alter_column("weight_kg", existing_type=sa.Text(), nullable=False)
