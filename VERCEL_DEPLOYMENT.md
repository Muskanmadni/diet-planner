# Deploying Diet Planner App on Vercel

## Prerequisites

1. Create a free Vercel account at [vercel.com](https://vercel.com)
2. Install Vercel CLI (optional): `npm i -g vercel`

## Environment Variables

Before deploying, you'll need to set the following environment variables in your Vercel project:

- `GEMINI_API_KEY`: Your Google Gemini API key for AI features
- `SECRET_KEY`: Secret key for Flask sessions (use a strong random string)
- `DATABASE_URL`: Database URL for production (e.g., PostgreSQL). If not set, the app will use SQLite for development.
- `AUTH0_CLIENT_ID`: Your Auth0 client ID (if using Auth0 authentication)
- `AUTH0_CLIENT_SECRET`: Your Auth0 client secret
- `AUTH0_DOMAIN`: Your Auth0 domain

## Deployment Methods

### Method 1: Git Integration (Recommended)

1. Push your code to a Git repository (GitHub, GitLab, or Bitbucket)
2. Visit [vercel.com/dashboard](https://vercel.com/dashboard) and click "Add New Project"
3. Select your repository
4. Vercel will automatically detect it's a Python project and configure the build
5. Add the environment variables listed above in the "Environment Variables" section
6. Click "Deploy"

### Method 2: Vercel CLI

1. Install the Vercel CLI: `npm install -g vercel`
2. Navigate to your project directory
3. Run `vercel`
4. Follow the prompts to link to your account and project
5. Set the environment variables when prompted

## Important Files

- `vercel.json`: Configures the build and deployment settings
- `wsgi.py`: Entry point for the Python application
- `requirements.txt`: Lists all Python dependencies
- `src/diet_planner/app.py`: Main Flask application

## Database Configuration

### For Development and Vercel Deployment (using SQLite):
The application now automatically uses SQLite for Vercel deployments to avoid psycopg2 build issues. The app will detect the deployment environment and force SQLite usage regardless of the DATABASE_URL setting.

**Note**: For Vercel deployment, the application is configured to use SQLite to avoid build issues with PostgreSQL dependencies. No hosted database setup is required for basic functionality, though if you choose to use PostgreSQL with a hosted database, you can set the DATABASE_URL environment variable.

## Notes

- All HTML templates are stored in the `src/diet_planner/` directory
- Static assets (images) are stored in `src/diet_planner/static/images/`
- The app includes authentication, nutrition tracking, recipe generation, and diet planning features

## Troubleshooting

If you encounter issues:
1. Check that all environment variables are properly set
2. Verify that your Git repository contains all necessary files
3. Make sure the `requirements.txt` file includes all dependencies
4. Review the build logs in your Vercel dashboard for specific error messages
5. For database issues in production, ensure you're using a hosted database service