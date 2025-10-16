from google_auth_oauthlib.flow import InstalledAppFlow
import json

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send'
]

def main():
    flow = InstalledAppFlow.from_client_secrets_file(
        'credentials.json', SCOPES)
    
    creds = flow.run_local_server(port=0)
    
    # Save the credentials
    token_data = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes
    }
    
    with open('gmail_token.json', 'w') as token_file:
        json.dump(token_data, token_file, indent=2)
    
    print("✅ Success! Token saved to gmail_token.json")

if __name__ == '__main__':
    main()