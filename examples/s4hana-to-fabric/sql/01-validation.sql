-- Run on the SQL analytics endpoint of lakehouse lh_sap_silver (Fabric).
-- Field names follow the standard extractor structures; confirm them in SAP with RSA3/RSA6
-- and adjust if your extractors are enhanced or use different fields.

-- TC-05: every table is present and not empty
SELECT 'sales_order_header' AS table_name, COUNT_BIG(*) AS row_count FROM dbo.sales_order_header
UNION ALL SELECT 'sales_order_item', COUNT_BIG(*) FROM dbo.sales_order_item
UNION ALL SELECT 'billing_item', COUNT_BIG(*) FROM dbo.billing_item
UNION ALL SELECT 'customer', COUNT_BIG(*) FROM dbo.customer
UNION ALL SELECT 'material', COUNT_BIG(*) FROM dbo.material;

-- TC-06: no duplicate business keys after MERGE (each query must return 0 rows)
SELECT VBELN, COUNT(*) AS n FROM dbo.sales_order_header GROUP BY VBELN HAVING COUNT(*) > 1;
SELECT VBELN, POSNR, COUNT(*) AS n FROM dbo.sales_order_item GROUP BY VBELN, POSNR HAVING COUNT(*) > 1;
SELECT VBELN, POSNR, COUNT(*) AS n FROM dbo.billing_item GROUP BY VBELN, POSNR HAVING COUNT(*) > 1;
SELECT KUNNR, COUNT(*) AS n FROM dbo.customer GROUP BY KUNNR HAVING COUNT(*) > 1;
SELECT MATNR, COUNT(*) AS n FROM dbo.material GROUP BY MATNR HAVING COUNT(*) > 1;

-- TC-07: referential checks (expected: 0 or a small, explainable number)
SELECT COUNT(*) AS items_without_header
FROM dbo.sales_order_item i
LEFT JOIN dbo.sales_order_header h ON h.VBELN = i.VBELN
WHERE h.VBELN IS NULL;

SELECT COUNT(*) AS items_without_material
FROM dbo.sales_order_item i
LEFT JOIN dbo.material m ON m.MATNR = i.MATNR
WHERE m.MATNR IS NULL;

-- TC-08: reconciliation with SAP — compare with the counts noted in SAP (see README, step 4)
SELECT COUNT(DISTINCT VBELN) AS sales_documents, COUNT_BIG(*) AS sales_items
FROM dbo.sales_order_item;

-- TC-09/10/11: inspect the test documents created/changed/deleted in SAP during the incremental test
-- Replace the document number with the one noted during the test.
SELECT * FROM dbo.sales_order_header WHERE VBELN = '<test-sales-document>';
SELECT * FROM dbo.sales_order_item   WHERE VBELN = '<test-sales-document>' ORDER BY POSNR;
