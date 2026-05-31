update public.policy_rules
set
  enabled = active,
  status = case
    when active then 'active'
    when synthetic is false then 'draft'
    else 'disabled'
  end
where source_type = 'seeded'
   or synthetic is true;
