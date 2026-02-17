-- Initialize the multi-tenant database
-- This runs on first container start

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create the public schema tables for platform-level data
-- Tenant registry lives in public schema
-- Per-tenant data lives in tenant_{slug} schemas

-- Ensure the platform user has schema creation privileges
ALTER USER platform CREATEDB;

-- Create a function to safely create tenant schemas
CREATE OR REPLACE FUNCTION create_tenant_schema(schema_name TEXT)
RETURNS VOID AS $$
BEGIN
    EXECUTE format('CREATE SCHEMA IF NOT EXISTS %I', schema_name);
    EXECUTE format('GRANT ALL ON SCHEMA %I TO platform', schema_name);
END;
$$ LANGUAGE plpgsql;

-- Create a function to get schema size
CREATE OR REPLACE FUNCTION get_schema_size(schema_name TEXT)
RETURNS BIGINT AS $$
DECLARE
    total_size BIGINT := 0;
BEGIN
    SELECT COALESCE(SUM(pg_total_relation_size(quote_ident(schemaname) || '.' || quote_ident(tablename))), 0)
    INTO total_size
    FROM pg_tables
    WHERE schemaname = schema_name;
    RETURN total_size;
END;
$$ LANGUAGE plpgsql;
