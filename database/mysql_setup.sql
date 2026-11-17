-- Django migrations create and evolve the project tables.
-- After migrations, optionally seed fictional linked records with:
-- python manage.py seed_demo_data
CREATE DATABASE IF NOT EXISTS ambulance_db
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
