#!/usr/bin/env python3
"""
Run the database migration to create the events table.
This script uses psycopg2 to directly connect to Supabase Postgres.
"""

import psycopg2
import os

# Supabase connection string
# Format: postgresql://postgres:[YOUR-PASSWORD]@db.exsoepsvmoseapulforp.supabase.co:5432/postgres
print("=" * 60)
print("DATABASE MIGRATION RUNNER")
print("=" * 60)

password = input("\nEnter your Supabase database password: ")
conn_string = f"postgresql://postgres:{password}@db.exsoepsvmoseapulforp.supabase.co:5432/postgres"

print("\n🔌 Connecting to database...")

try:
    conn = psycopg2.connect(conn_string)
    conn.autocommit = True
    cursor = conn.cursor()

    print("✅ Connected successfully\n")

    # Read migration file
    with open("migrations/001_create_events_table.sql", "r") as f:
        migration_sql = f.read()

    print("📄 Running migration...")
    print("-" * 60)

    # Execute migration
    cursor.execute(migration_sql)

    print("✅ Migration completed successfully!")
    print("\n📊 Verifying table creation...")

    # Verify table exists
    cursor.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'events'
        ORDER BY ordinal_position;
    """)

    columns = cursor.fetchall()
    print(f"\n✅ Table 'events' created with {len(columns)} columns:")
    for col_name, col_type in columns[:5]:  # Show first 5
        print(f"   - {col_name}: {col_type}")
    if len(columns) > 5:
        print(f"   ... and {len(columns) - 5} more columns")

    # Check indexes
    cursor.execute("""
        SELECT indexname
        FROM pg_indexes
        WHERE tablename = 'events';
    """)
    indexes = cursor.fetchall()
    print(f"\n✅ {len(indexes)} indexes created:")
    for idx in indexes:
        print(f"   - {idx[0]}")

    cursor.close()
    conn.close()

    print("\n" + "=" * 60)
    print("✅ MIGRATION COMPLETE")
    print("=" * 60)
    print("\n💡 Next step: Run import_events.py to load data")

except psycopg2.Error as e:
    print(f"\n❌ Database error: {e}")
    print("\n💡 Troubleshooting:")
    print("   1. Check your database password")
    print("   2. Ensure your Supabase project is active (not paused)")
    print("   3. Check network connection")
except FileNotFoundError:
    print("\n❌ Migration file not found: migrations/001_create_events_table.sql")
    print("   Make sure you're running this from the project root directory")
except Exception as e:
    print(f"\n❌ Unexpected error: {e}")
