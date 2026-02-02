"""First-run setup wizard for Google OAuth2 authentication."""

import os
import sys
import json

def main():
    print("=" * 50)
    print("Cold Email Outreach — Setup Wizard")
    print("=" * 50)
    print()

    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    os.makedirs(data_dir, exist_ok=True)
    creds_path = os.path.join(data_dir, 'credentials.json')

    # Check for credentials.json
    has_creds = os.path.exists(creds_path)
    skip_google = False

    if not has_creds:
        print("Step 1: Google API Credentials")
        print("-" * 40)
        print("No credentials.json found.")
        print("You can set up Google APIs later by saving credentials.json")
        print(f"to: {creds_path}")
        print()
        choice = input("Skip Google API setup for now? [Y/n]: ").strip().lower()
        if choice != 'n':
            skip_google = True
            print("Skipping Google API setup.")
        else:
            print()
            print("1. Go to https://console.cloud.google.com/")
            print("2. Create a project (or select existing)")
            print("3. Enable 'Gmail API' and 'Google Sheets API'")
            print("4. Go to Credentials → Create OAuth 2.0 Client ID")
            print("   - Application type: Desktop app")
            print("5. Download the JSON file")
            print(f"6. Save it as: {creds_path}")
            print()
            input("Press Enter once you've saved credentials.json...")

            if not os.path.exists(creds_path):
                print("credentials.json not found. Skipping Google API setup.")
                skip_google = True
            else:
                has_creds = True
    else:
        print(f"Found credentials at {creds_path}")

    if has_creds and not skip_google:
        # Gmail OAuth
        print()
        print("Step 2: Gmail Authentication")
        print("-" * 40)
        print("A browser window will open for Gmail authorization.")
        input("Press Enter to continue...")

        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            gmail_scopes = [
                'https://www.googleapis.com/auth/gmail.send',
                'https://www.googleapis.com/auth/gmail.readonly',
            ]
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, gmail_scopes)
            creds = flow.run_local_server(port=8090)
            token_path = os.path.join(data_dir, 'gmail_token.json')
            with open(token_path, 'w') as f:
                f.write(creds.to_json())
            print("Gmail connected successfully!")
        except Exception as e:
            print(f"Gmail auth failed: {e}")
            print("You can retry later by running this wizard again.")

        # Sheets OAuth
        print()
        print("Step 3: Google Sheets Authentication")
        print("-" * 40)
        print("A browser window will open for Sheets authorization.")
        input("Press Enter to continue...")

        try:
            sheets_scopes = ['https://www.googleapis.com/auth/spreadsheets']
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, sheets_scopes)
            creds = flow.run_local_server(port=8091)
            token_path = os.path.join(data_dir, 'sheets_token.json')
            with open(token_path, 'w') as f:
                f.write(creds.to_json())
            print("Google Sheets connected successfully!")
        except Exception as e:
            print(f"Sheets auth failed: {e}")
            print("You can retry later.")
    else:
        print()
        print("Skipped Steps 2-3 (Gmail/Sheets auth).")
        print("Re-run this wizard after adding credentials.json to connect.")

    # .env check
    print()
    print("Step 4: Environment Variables")
    print("-" * 40)
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if not os.path.exists(env_path):
        example_path = os.path.join(os.path.dirname(__file__), '.env.example')
        if os.path.exists(example_path):
            import shutil
            shutil.copy(example_path, env_path)
            print(f"Created .env from .env.example")
            print(f"Edit {env_path} to fill in your API keys.")
        else:
            print("No .env file found. Create one from .env.example.")
    else:
        print(".env file exists.")

    # Init database
    print()
    print("Step 5: Database Initialization")
    print("-" * 40)
    sys.path.insert(0, os.path.dirname(__file__))
    from backend.database import init_db
    init_db()
    print("Database initialized.")

    print()
    print("=" * 50)
    print("Setup complete!")
    print()
    print("Start the app with:")
    print("  python backend/app.py")
    print()
    print("Then open http://localhost:5000")
    print("=" * 50)


if __name__ == '__main__':
    main()
