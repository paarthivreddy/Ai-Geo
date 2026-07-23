"""Initial schema for GeoCare AI.

Revision ID: 001
Revises:
Create Date: 2025-07-20 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enums
    op.execute("CREATE TYPE user_role AS ENUM ('admin', 'analyst', 'viewer')")
    op.execute("CREATE TYPE user_status AS ENUM ('active', 'inactive', 'locked')")
    op.execute("CREATE TYPE job_status AS ENUM ('pending', 'profiling', 'mapping', 'queued', 'processing', 'completed', 'failed', 'cancelled')")
    op.execute("CREATE TYPE review_status AS ENUM ('auto', 'needs_review', 'manual_verified', 'rejected')")
    op.execute("CREATE TYPE confidence_tier AS ENUM ('high', 'medium', 'low', 'unverified')")
    op.execute("CREATE TYPE match_method AS ENUM ('exact', 'fuzzy', 'inferred', 'manual')")
    op.execute("CREATE TYPE chunk_status AS ENUM ('pending', 'processing', 'completed', 'failed')")
    op.execute("CREATE TYPE processing_method AS ENUM ('normalization', 'parsing', 'pin_resolution', 'locality_match', 'spell_correction', 'hierarchy_enrichment', 'validation_correction', 'manual_override')")
    op.execute("CREATE TYPE data_source AS ENUM ('india_post', 'osm', 'census', 'libpostal', 'rapidfuzz', 'manual', 'inferred')")
    op.execute("CREATE TYPE office_type AS ENUM ('head', 'sub', 'branch')")
    op.execute("CREATE TYPE delivery_status AS ENUM ('delivery', 'non_delivery')")
    op.execute("CREATE TYPE locality_source AS ENUM ('india_post', 'osm', 'census', 'merged')")

    # Users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('full_name', sa.String(255), nullable=False),
        sa.Column('role', sa.Enum('admin', 'analyst', 'viewer', name='user_role'), nullable=False, server_default='viewer'),
        sa.Column('status', sa.Enum('active', 'inactive', 'locked', name='user_status'), nullable=False, server_default='active'),
        sa.Column('salt', sa.String(32), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True)),
        sa.Column('failed_login_attempts', sa.Integer(), default=0),
        sa.Column('locked_until', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('ix_users_email', 'users', ['email'])
    op.create_index('ix_users_status', 'users', ['status'], postgresql_where=sa.text("status = 'active'"))

    # Processing jobs table
    op.create_table(
        'processing_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False, index=True),
        sa.Column('filename', sa.String(500), nullable=False),
        sa.Column('original_file_path', sa.String(1000)),
        sa.Column('parquet_file_path', sa.String(1000)),
        sa.Column('total_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_columns', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('column_mapping', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('detected_address_columns', postgresql.ARRAY(sa.Text()), nullable=False, server_default='{}'),
        sa.Column('status', sa.Enum('pending', 'profiling', 'mapping', 'queued', 'processing', 'completed', 'failed', 'cancelled', name='job_status'), nullable=False, server_default='pending', index=True),
        sa.Column('progress_pct', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('processed_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('succeeded_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('manual_review_rows', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('chunk_size', sa.Integer(), nullable=False, server_default='50000'),
        sa.Column('total_chunks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completed_chunks', postgresql.ARRAY(sa.Integer()), nullable=False, server_default='{}'),
        sa.Column('failed_chunks', postgresql.ARRAY(sa.Integer()), nullable=False, server_default='{}'),
        sa.Column('error_message', sa.Text()),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('ix_jobs_user_status', 'processing_jobs', ['user_id', 'status'])
    op.create_index('ix_jobs_created_at_desc', 'processing_jobs', ['created_at'], postgresql_using='btree', postgresql_ops={'created_at': 'DESC'})
    op.create_index('ix_jobs_status_active', 'processing_jobs', ['status'], postgresql_where=sa.text("status IN ('processing', 'queued')"))

    # Job chunks table
    op.create_table(
        'job_chunks',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('job_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('processing_jobs.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('storage_path', sa.String(1000), nullable=False),
        sa.Column('row_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.Enum('pending', 'processing', 'completed', 'failed', name='chunk_status'), nullable=False, server_default='pending'),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('error_message', sa.Text()),
        sa.Column('worker_id', sa.String(100)),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.UniqueConstraint('job_id', 'chunk_index', name='uq_job_chunk_index'),
    )
    op.create_index('ix_chunks_job_status', 'job_chunks', ['job_id', 'status'])
    op.create_index('ix_chunks_worker', 'job_chunks', ['worker_id'], postgresql_where=sa.text("status = 'processing'"))

    # Patient records table (partitioned by job_id)
    op.create_table(
        'patient_records',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('job_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('processing_jobs.id', ondelete='CASCADE'), primary_key=True, nullable=False),
        sa.Column('row_index', sa.Integer(), nullable=False),
        sa.Column('patient_id_hash', sa.String(64), nullable=False, index=True),
        sa.Column('original_address', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('normalized_address', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('parsed_address', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('enriched_address', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('confidence_score', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default='{}'),
        sa.Column('confidence_tier', sa.Enum('high', 'medium', 'low', 'unverified', name='confidence_tier'), nullable=False, server_default='unverified', index=True),
        sa.Column('match_method', sa.Enum('exact', 'fuzzy', 'inferred', 'manual', name='match_method'), nullable=False, server_default='manual'),
        sa.Column('review_status', sa.Enum('auto', 'needs_review', 'manual_verified', 'rejected', name='review_status'), nullable=False, server_default='auto', index=True),
        sa.Column('reviewed_by', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('reviewed_at', sa.DateTime(timezone=True)),
        sa.Column('review_notes', sa.Text()),
        sa.Column('geometry', sa.Text()),  # WKT format
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    # Partition by hash of job_id (16 partitions)
    op.execute("""
        ALTER TABLE patient_records
        SET (autovacuum_vacuum_scale_factor = 0.05)
    """)
    op.create_index('ix_records_job_id', 'patient_records', ['job_id'])
    op.create_index('ix_records_review_status', 'patient_records', ['review_status'], postgresql_where=sa.text("review_status != 'auto'"))
    op.create_index('ix_records_confidence_tier', 'patient_records', ['confidence_tier'])
    op.create_index('ix_records_patient_hash', 'patient_records', ['patient_id_hash'])

    # Job quality stats table
    op.create_table(
        'job_quality_stats',
        sa.Column('job_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('processing_jobs.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('total_records', sa.Integer()),
        sa.Column('complete_addresses_before', sa.Integer()),
        sa.Column('missing_pincode_before', sa.Integer()),
        sa.Column('missing_locality_before', sa.Integer()),
        sa.Column('missing_city_before', sa.Integer()),
        sa.Column('missing_district_before', sa.Integer()),
        sa.Column('missing_state_before', sa.Integer()),
        sa.Column('invalid_addresses_before', sa.Integer()),
        sa.Column('duplicate_addresses_before', sa.Integer()),
        sa.Column('overall_quality_before', sa.Float()),
        sa.Column('pincodes_added', sa.Integer()),
        sa.Column('cities_added', sa.Integer()),
        sa.Column('districts_added', sa.Integer()),
        sa.Column('states_added', sa.Integer()),
        sa.Column('spell_corrections', sa.Integer()),
        sa.Column('improved_records', sa.Integer()),
        sa.Column('manual_review_records', sa.Integer()),
        sa.Column('final_quality_score', sa.Float()),
        sa.Column('improvement_percentage', sa.Float()),
        sa.Column('confidence_high', sa.Integer(), default=0),
        sa.Column('confidence_medium', sa.Integer(), default=0),
        sa.Column('confidence_low', sa.Integer(), default=0),
        sa.Column('confidence_unverified', sa.Integer(), default=0),
        sa.Column('profiling_time', sa.Float()),
        sa.Column('processing_time', sa.Float()),
        sa.Column('reporting_time', sa.Float()),
        sa.Column('export_time', sa.Float()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )

    # Audit entries table (partitioned by date - range partitioning)
    op.create_table(
        'audit_entries',
        sa.Column('id', postgresql.UUID(as_uuid=False), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('record_id', postgresql.UUID(as_uuid=False), nullable=False, index=True),
        sa.Column('job_id', postgresql.UUID(as_uuid=False), nullable=False, index=True),
        sa.Column('field_name', sa.String(100), nullable=False, index=True),
        sa.Column('old_value', sa.Text()),
        sa.Column('new_value', sa.Text()),
        sa.Column('processing_method', sa.Enum('normalization', 'parsing', 'pin_resolution', 'locality_match', 'spell_correction', 'hierarchy_enrichment', 'validation_correction', 'manual_override', name='processing_method'), nullable=False),
        sa.Column('confidence', sa.Integer(), nullable=False),
        sa.Column('source_dataset', sa.Enum('india_post', 'osm', 'census', 'libpostal', 'rapidfuzz', 'manual', 'inferred', name='data_source'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()'), index=True),
        sa.CheckConstraint('confidence BETWEEN 0 AND 100', name='ck_audit_confidence'),
    )
    op.create_index('ix_audit_created_at_desc', 'audit_entries', ['created_at'], postgresql_using='btree', postgresql_ops={'created_at': 'DESC'})

    # PIN code directory table
    op.create_table(
        'pincode_directory',
        sa.Column('pincode', sa.String(6), primary_key=True),
        sa.Column('office_name', sa.String(255), nullable=False),
        sa.Column('office_type', sa.Enum('head', 'sub', 'branch', name='office_type'), nullable=False),
        sa.Column('delivery_status', sa.Enum('delivery', 'non_delivery', name='delivery_status'), nullable=False),
        sa.Column('district', sa.String(100), nullable=False, index=True),
        sa.Column('state', sa.String(100), nullable=False, index=True),
        sa.Column('taluk', sa.String(100)),
        sa.Column('circle', sa.String(100)),
        sa.Column('region', sa.String(100)),
        sa.Column('division', sa.String(100)),
        sa.Column('latitude', sa.Float()),
        sa.Column('longitude', sa.Float()),
        sa.Column('localities', postgresql.ARRAY(sa.Text()), nullable=False, server_default='{}'),
        sa.Column('source_version', sa.String(50), nullable=False),
        sa.Column('loaded_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.CheckConstraint("pincode ~ '^[1-8][0-9]{5}$'", name='ck_valid_pincode'),
    )
    op.create_index('ix_pincode_district_state', 'pincode_directory', ['district', 'state'])
    op.create_index('ix_pincode_taluk', 'pincode_directory', ['taluk'])
    op.create_index('ix_pincode_geo', 'pincode_directory', ['latitude', 'longitude'], postgresql_where=sa.text('latitude IS NOT NULL AND longitude IS NOT NULL'))

    # Locality dictionary table
    op.create_table(
        'locality_dictionary',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('canonical_name', sa.String(255), nullable=False, index=True),
        sa.Column('aliases', postgresql.ARRAY(sa.Text()), nullable=False, server_default='{}'),
        sa.Column('pincode', sa.String(6), sa.ForeignKey('pincode_directory.pincode'), nullable=False, index=True),
        sa.Column('city', sa.String(100), nullable=False, index=True),
        sa.Column('district', sa.String(100), nullable=False, index=True),
        sa.Column('state', sa.String(100), nullable=False, index=True),
        sa.Column('latitude', sa.Float()),
        sa.Column('longitude', sa.Float()),
        sa.Column('population', sa.BigInteger()),
        sa.Column('source', sa.Enum('india_post', 'osm', 'census', 'merged', name='locality_source'), nullable=False),
        sa.Column('source_version', sa.String(50)),
        sa.Column('loaded_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.CheckConstraint(
            "(latitude IS NULL AND longitude IS NULL) OR "
            "(latitude BETWEEN 6.0 AND 38.0 AND longitude BETWEEN 68.0 AND 98.0)",
            name='ck_valid_coords'
        ),
    )
    op.create_index('ix_locality_aliases_gin', 'locality_dictionary', ['aliases'], postgresql_using='gin')
    op.create_index('ix_locality_city_district', 'locality_dictionary', ['city', 'district'])

    # Census hierarchy table
    op.create_table(
        'census_hierarchy',
        sa.Column('state_code', sa.String(2), primary_key=True),
        sa.Column('state_name', sa.String(100), nullable=False),
        sa.Column('district_code', sa.String(4)),
        sa.Column('district_name', sa.String(100)),
        sa.Column('subdistrict_code', sa.String(6)),
        sa.Column('subdistrict_name', sa.String(100)),
        sa.Column('village_code', sa.String(8)),
        sa.Column('village_name', sa.String(255)),
        sa.Column('level', sa.String(20), nullable=False),
        sa.Column('population', sa.BigInteger()),
        sa.Column('latitude', sa.Float()),
        sa.Column('longitude', sa.Float()),
        sa.Column('source_version', sa.String(50)),
        sa.Column('loaded_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )
    op.create_index('ix_census_district', 'census_hierarchy', ['district_code'])
    op.create_index('ix_census_subdistrict', 'census_hierarchy', ['subdistrict_code'])
    op.create_index('ix_census_village', 'census_hierarchy', ['village_code'])
    op.create_index('ix_census_names', 'census_hierarchy', ['state_name', 'district_name', 'village_name'])

    # Geography dataset versions table
    op.create_table(
        'geography_dataset_versions',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('dataset_name', sa.String(50), nullable=False),
        sa.Column('version', sa.String(50), nullable=False),
        sa.Column('source_url', sa.Text()),
        sa.Column('checksum_sha256', sa.String(64)),
        sa.Column('row_count', sa.BigInteger()),
        sa.Column('status', sa.String(20), nullable=False, server_default='loading'),
        sa.Column('error_message', sa.Text()),
        sa.Column('loaded_by', postgresql.UUID(as_uuid=False), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('loaded_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('activated_at', sa.DateTime(timezone=True)),
        sa.Column('archived_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('dataset_name', 'version', name='uq_dataset_version'),
    )
    op.create_index('ix_dataset_active', 'geography_dataset_versions', ['dataset_name', 'status'], postgresql_where=sa.text("status = 'loaded'"))


def downgrade() -> None:
    op.drop_table('geography_dataset_versions')
    op.drop_table('census_hierarchy')
    op.drop_table('locality_dictionary')
    op.drop_table('pincode_directory')
    op.drop_table('audit_entries')
    op.drop_table('job_quality_stats')
    op.drop_table('patient_records')
    op.drop_table('job_chunks')
    op.drop_table('processing_jobs')
    op.drop_table('users')

    op.execute("DROP TYPE IF EXISTS locality_source")
    op.execute("DROP TYPE IF EXISTS delivery_status")
    op.execute("DROP TYPE IF EXISTS office_type")
    op.execute("DROP TYPE IF EXISTS data_source")
    op.execute("DROP TYPE IF EXISTS processing_method")
    op.execute("DROP TYPE IF EXISTS chunk_status")
    op.execute("DROP TYPE IF EXISTS match_method")
    op.execute("DROP TYPE IF EXISTS confidence_tier")
    op.execute("DROP TYPE IF EXISTS review_status")
    op.execute("DROP TYPE IF EXISTS job_status")
    op.execute("DROP TYPE IF EXISTS user_status")
    op.execute("DROP TYPE IF EXISTS user_role")