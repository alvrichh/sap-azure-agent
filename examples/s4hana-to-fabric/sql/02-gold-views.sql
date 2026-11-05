-- Gold layer as views on the SQL analytics endpoint (lh_sap_silver).
-- Basis for a Direct Lake semantic model or Power BI reports.
-- For heavy volumes, materialize these as Delta tables (notebook or warehouse) instead of views.

CREATE SCHEMA gold;
GO

CREATE VIEW gold.dim_customer AS
SELECT KUNNR AS customer_id, NAME1 AS customer_name, LAND1 AS country, ORT01 AS city
FROM dbo.customer;
GO

CREATE VIEW gold.dim_material AS
SELECT MATNR AS material_id, MTART AS material_type, MATKL AS material_group, MEINS AS base_unit
FROM dbo.material;
GO

CREATE VIEW gold.fact_sales_order_item AS
SELECT
    i.VBELN  AS sales_document,
    i.POSNR  AS item,
    h.AUDAT  AS document_date,
    h.KUNNR  AS customer_id,
    i.MATNR  AS material_id,
    i.WERKS  AS plant,
    h.VKORG  AS sales_org,
    i.KWMENG AS order_quantity,
    i.NETWR  AS net_value,
    i.WAERK  AS currency
FROM dbo.sales_order_item i
JOIN dbo.sales_order_header h ON h.VBELN = i.VBELN;
GO

CREATE VIEW gold.fact_billing_item AS
SELECT
    b.VBELN  AS billing_document,
    b.POSNR  AS item,
    b.FKDAT  AS billing_date,
    b.AUBEL  AS sales_document,
    b.MATNR  AS material_id,
    b.FKIMG  AS billed_quantity,
    b.NETWR  AS net_value,
    b.WAERK  AS currency
FROM dbo.billing_item b;
GO

-- TC-12: the gold layer answers a business question
SELECT TOP 10 c.customer_name, SUM(f.net_value) AS net_sales, f.currency
FROM gold.fact_sales_order_item f
JOIN gold.dim_customer c ON c.customer_id = f.customer_id
GROUP BY c.customer_name, f.currency
ORDER BY net_sales DESC;
