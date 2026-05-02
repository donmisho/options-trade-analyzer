-- Get all external (Entra) users
  SELECT name, type_desc, authentication_type_desc 
  FROM sys.database_principals 
  WHERE type IN ('E', 'X');

  -- Get role memberships
  SELECT r.name AS role_name, m.name AS member_name
  FROM sys.database_role_members rm
  JOIN sys.database_principals r ON rm.role_principal_id = r.principal_id
  JOIN sys.database_principals m ON rm.member_principal_id = m.principal_id
  WHERE m.type IN ('E', 'X');

  -- Get full DB schema overview (table count, sproc count, etc.)
  SELECT 
    (SELECT COUNT(*) FROM sys.tables) AS table_count,
    (SELECT COUNT(*) FROM sys.procedures) AS procedure_count,
    (SELECT COUNT(*) FROM sys.views) AS view_count;