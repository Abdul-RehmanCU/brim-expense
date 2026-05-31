insert into public.departments (name, manager_name, monthly_budget_cad, quarterly_budget_cad, synthetic)
values
  ('Marketing', 'Maya Patel', 35000.00, 105000.00, true),
  ('Sales', 'Jordan Lee', 42000.00, 126000.00, true),
  ('Engineering', 'Priya Shah', 28000.00, 84000.00, true),
  ('Operations', 'Daniel Brooks', 24000.00, 72000.00, true),
  ('Finance', 'Amelia Stone', 18000.00, 54000.00, true),
  ('HR', 'Noah Wilson', 12000.00, 36000.00, true),
  ('Customer Success', 'Elena Garcia', 22000.00, 66000.00, true),
  ('Executive', 'Avery Morgan', 30000.00, 90000.00, true)
on conflict (name) do update set
  manager_name = excluded.manager_name,
  monthly_budget_cad = excluded.monthly_budget_cad,
  quarterly_budget_cad = excluded.quarterly_budget_cad,
  synthetic = true;
