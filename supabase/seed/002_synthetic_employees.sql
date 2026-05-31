insert into public.employees (department_id, full_name, email, role, synthetic)
select d.id, e.full_name, e.email, e.role, true
from (
  values
    ('Marketing', 'Sarah Chen', 'sarah.chen@brim-demo.example', 'Marketing Manager'),
    ('Marketing', 'Maya Patel', 'maya.patel@brim-demo.example', 'VP Marketing'),
    ('Marketing', 'Leo Martin', 'leo.martin@brim-demo.example', 'Events Specialist'),
    ('Marketing', 'Nina Roy', 'nina.roy@brim-demo.example', 'Demand Generation Lead'),
    ('Marketing', 'Owen Kim', 'owen.kim@brim-demo.example', 'Content Strategist'),
    ('Marketing', 'Grace Young', 'grace.young@brim-demo.example', 'Brand Designer'),
    ('Sales', 'Jordan Lee', 'jordan.lee@brim-demo.example', 'Sales Director'),
    ('Sales', 'Camila Torres', 'camila.torres@brim-demo.example', 'Account Executive'),
    ('Sales', 'Ethan Park', 'ethan.park@brim-demo.example', 'Account Executive'),
    ('Sales', 'Sofia Nguyen', 'sofia.nguyen@brim-demo.example', 'Sales Development Rep'),
    ('Sales', 'Liam Scott', 'liam.scott@brim-demo.example', 'Regional Manager'),
    ('Sales', 'Aisha Khan', 'aisha.khan@brim-demo.example', 'Customer Account Lead'),
    ('Engineering', 'Priya Shah', 'priya.shah@brim-demo.example', 'Engineering Director'),
    ('Engineering', 'Marcus Green', 'marcus.green@brim-demo.example', 'Staff Engineer'),
    ('Engineering', 'Iris Wong', 'iris.wong@brim-demo.example', 'Frontend Engineer'),
    ('Engineering', 'Theo Bennett', 'theo.bennett@brim-demo.example', 'Platform Engineer'),
    ('Engineering', 'Hana Suzuki', 'hana.suzuki@brim-demo.example', 'QA Engineer'),
    ('Engineering', 'Victor Allen', 'victor.allen@brim-demo.example', 'DevOps Engineer'),
    ('Operations', 'Daniel Brooks', 'daniel.brooks@brim-demo.example', 'Operations Director'),
    ('Operations', 'Mila Adams', 'mila.adams@brim-demo.example', 'Office Manager'),
    ('Operations', 'Jonah Reed', 'jonah.reed@brim-demo.example', 'Procurement Specialist'),
    ('Operations', 'Keira Hall', 'keira.hall@brim-demo.example', 'Logistics Coordinator'),
    ('Operations', 'Samir Das', 'samir.das@brim-demo.example', 'Facilities Lead'),
    ('Operations', 'Rachel Moore', 'rachel.moore@brim-demo.example', 'Vendor Manager'),
    ('Finance', 'Amelia Stone', 'amelia.stone@brim-demo.example', 'Finance Director'),
    ('Finance', 'Ben Carter', 'ben.carter@brim-demo.example', 'Controller'),
    ('Finance', 'Laila Ahmed', 'laila.ahmed@brim-demo.example', 'Financial Analyst'),
    ('Finance', 'Chris Evans', 'chris.evans@brim-demo.example', 'Accounts Payable Specialist'),
    ('Finance', 'Mei Lin', 'mei.lin@brim-demo.example', 'Payroll Specialist'),
    ('Finance', 'Ravi Mehta', 'ravi.mehta@brim-demo.example', 'FP&A Analyst'),
    ('HR', 'Noah Wilson', 'noah.wilson@brim-demo.example', 'HR Director'),
    ('HR', 'Tara Singh', 'tara.singh@brim-demo.example', 'People Partner'),
    ('HR', 'Ella King', 'ella.king@brim-demo.example', 'Recruiter'),
    ('HR', 'Mateo Cruz', 'mateo.cruz@brim-demo.example', 'HR Coordinator'),
    ('HR', 'Zoe Clark', 'zoe.clark@brim-demo.example', 'Learning Specialist'),
    ('Customer Success', 'Elena Garcia', 'elena.garcia@brim-demo.example', 'CS Director'),
    ('Customer Success', 'Dylan Price', 'dylan.price@brim-demo.example', 'Customer Success Manager'),
    ('Customer Success', 'Mira Kapoor', 'mira.kapoor@brim-demo.example', 'Customer Success Manager'),
    ('Customer Success', 'Tyler James', 'tyler.james@brim-demo.example', 'Implementation Lead'),
    ('Customer Success', 'Olivia Brown', 'olivia.brown@brim-demo.example', 'Support Manager'),
    ('Customer Success', 'Mateo Rivera', 'mateo.rivera@brim-demo.example', 'Onboarding Specialist'),
    ('Executive', 'Avery Morgan', 'avery.morgan@brim-demo.example', 'CEO'),
    ('Executive', 'Quinn Foster', 'quinn.foster@brim-demo.example', 'COO'),
    ('Executive', 'Harper Blake', 'harper.blake@brim-demo.example', 'CRO'),
    ('Executive', 'Rowan Mills', 'rowan.mills@brim-demo.example', 'Chief of Staff'),
    ('Executive', 'Sienna Ward', 'sienna.ward@brim-demo.example', 'Executive Assistant'),
    ('Sales', 'Mason Hill', 'mason.hill@brim-demo.example', 'Partnerships Lead'),
    ('Engineering', 'Clara Hughes', 'clara.hughes@brim-demo.example', 'Data Engineer'),
    ('Marketing', 'Julian Brooks', 'julian.brooks@brim-demo.example', 'Product Marketing Manager'),
    ('Operations', 'Anika Rao', 'anika.rao@brim-demo.example', 'Travel Coordinator')
) as e(department_name, full_name, email, role)
join public.departments d on d.name = e.department_name
on conflict (email) do update set
  department_id = excluded.department_id,
  full_name = excluded.full_name,
  role = excluded.role,
  synthetic = true;

update public.employees employee
set manager_employee_id = manager.id
from public.employees manager
join public.departments d on d.manager_name = manager.full_name
where employee.department_id = d.id
  and employee.id <> manager.id
  and employee.manager_employee_id is distinct from manager.id;
