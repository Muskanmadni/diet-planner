-- supabase/seed.sql

INSERT INTO auth.users (instance_id, id, aud, role, email, encrypted_password, email_confirmed_at, raw_app_meta_data, raw_user_meta_data, created_at, updated_at)
VALUES (
  '00000000-0000-0000-0000-000000000000',
  'f5e0f7d7-19a5-c2d9-a4fc-ab88f3e1624c',
  'authenticated',
  'authenticated',
  'testuser@gmail.com',
  '$2a$10$4be5Of7d719a5cc2d9a4fcab88f3e1624c021228ef67e1c6d1100',  -- yeh hashed password hai
  now(),
  '{"provider":"email","providers":["email"]}',
  '{"name":"Test User","gender":"male","lose":2.0,"current_weight":133.33,"goal_weight":61.20,"height":162,"daily_calories":2025}',
  now(),
  now()
) ON CONFLICT (id) DO NOTHING;

INSERT INTO public.profiles (id, email, name, gender, current_weight, goal_weight, height, daily_calories, lose, subscription_tier, subscription_start_date, subscription_end_date, subscription_status)
VALUES (
  'f5e0f7d7-19a5-c2d9-a4fc-ab88f3e1624c',
  'testuser@gmail.com',
  'Test User',
  'male',
  133.33,
  61.20,
  162,
  2025,
  2.0,
  'free',
  '2025-11-18',
  '2025-12-18',
  'active'
) ON CONFLICT (id) DO UPDATE SET subscription_status = 'active';