-- One-time Snowflake setup for the SAP -> Snowflake test case.
-- Run as a user with ACCOUNTADMIN (storage integration) and SECURITYADMIN/SYSADMIN (roles, objects).
-- Statement syntax follows the Snowflake documentation; it is not covered by Microsoft Learn (see README, UV items).
-- No secrets here: the service user authenticates with a key pair; only the PUBLIC key goes into Snowflake.

-- 1. Role, warehouse, database and schemas -------------------------------------------------------
USE ROLE SECURITYADMIN;
CREATE ROLE IF NOT EXISTS ADF_SAP_LOADER COMMENT = 'Azure Data Factory loads SAP data';

USE ROLE SYSADMIN;
CREATE WAREHOUSE IF NOT EXISTS ADF_SAP_WH
  WAREHOUSE_SIZE = 'XSMALL' AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE;
CREATE DATABASE IF NOT EXISTS SAP_DB;
CREATE SCHEMA IF NOT EXISTS SAP_DB.SAP_LANDING COMMENT = 'Truncated and reloaded on every run';
CREATE SCHEMA IF NOT EXISTS SAP_DB.SAP_CORE COMMENT = 'Merged SAP data with load metadata';

-- 2. Least-privilege grants for the loader role ------------------------------------------------
GRANT USAGE ON WAREHOUSE ADF_SAP_WH TO ROLE ADF_SAP_LOADER;
GRANT USAGE ON DATABASE SAP_DB TO ROLE ADF_SAP_LOADER;
GRANT USAGE ON SCHEMA SAP_DB.SAP_LANDING TO ROLE ADF_SAP_LOADER;
GRANT USAGE ON SCHEMA SAP_DB.SAP_CORE TO ROLE ADF_SAP_LOADER;
-- The connector creates a temporary external stage for COPY INTO in the session schema (linked service schema)
GRANT CREATE STAGE ON SCHEMA SAP_DB.SAP_LANDING TO ROLE ADF_SAP_LOADER;
GRANT SELECT, INSERT, TRUNCATE ON FUTURE TABLES IN SCHEMA SAP_DB.SAP_LANDING TO ROLE ADF_SAP_LOADER;
GRANT SELECT, INSERT, UPDATE ON FUTURE TABLES IN SCHEMA SAP_DB.SAP_CORE TO ROLE ADF_SAP_LOADER;
-- (no DELETE on the core tables: the pipeline only inserts and updates)

-- 3. Storage integration: Snowflake reads the Azure staging container with its own Entra ID app, no SAS
USE ROLE ACCOUNTADMIN;
CREATE STORAGE INTEGRATION IF NOT EXISTS ADF_SAP_AZURE_INT
  TYPE = EXTERNAL_STAGE
  STORAGE_PROVIDER = 'AZURE'
  ENABLED = TRUE
  AZURE_TENANT_ID = '<tenant-id>'
  STORAGE_ALLOWED_LOCATIONS = ('azure://<storage-account-name>.blob.core.windows.net/snowflake-staging/');
GRANT USAGE ON INTEGRATION ADF_SAP_AZURE_INT TO ROLE ADF_SAP_LOADER;
-- Open AZURE_CONSENT_URL as a tenant admin and accept; AZURE_MULTI_TENANT_APP_NAME is the app to grant
-- "Storage Blob Data Reader" on the staging container (bicep/snowflake-staging.bicep does the role assignment).
DESC STORAGE INTEGRATION ADF_SAP_AZURE_INT;

-- 4. Service user with key-pair authentication ------------------------------------------------
USE ROLE SECURITYADMIN;
CREATE USER IF NOT EXISTS ADF_SAP_SVC
  TYPE = SERVICE
  DEFAULT_ROLE = ADF_SAP_LOADER
  DEFAULT_WAREHOUSE = ADF_SAP_WH
  DEFAULT_NAMESPACE = SAP_DB.SAP_LANDING
  RSA_PUBLIC_KEY = '<rsa-public-key-body>';
GRANT ROLE ADF_SAP_LOADER TO USER ADF_SAP_SVC;
-- Recommended for production: a network policy that allows only the Azure integration runtime egress IPs.
