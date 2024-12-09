from telethon.sync import TelegramClient
import asyncio
import re
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Telegram API credentials from environment variables
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
BOT_USERNAME = os.getenv('BOT_USERNAME')

# Google Sheets credentials
GOOGLE_SHEETS_CREDENTIALS = os.getenv('GOOGLE_SHEETS_CREDENTIALS')

# File paths
WALLET_FILE = 'wallets.txt'
RESULTS_FILE = 'results.txt'
WINNERS_FILE = 'winners.txt'

# Filters
MIN_MEDIAN_ROI = 35
MIN_HOLD_TIME_MINUTES = 30
MIN_WIN_RATE = 65

# Function to wait for account information and add a delay between requests
async def wait_for_account_info(conv, timeout=30, delay_after_response=12):
    while timeout > 0:
        response = await conv.get_response()
        if "Checking wallet..." not in response.text:
            await asyncio.sleep(delay_after_response)
            return response.text
        await asyncio.sleep(1)
        timeout -= 1
    return None

# Function to analyze wallet results
def analyze_wallet(data):
    try:
        # Sanitize data by removing backticks and other unwanted characters
        data = data.replace('`', '').strip()
        
        # Extract metrics using regex
        winrate_match = re.search(r'🏆\s*Winrate:\s*([\d.]+)%', data)
        roi_match = re.search(r'📈\s*ROI:\s*([\d.]+)%', data)
        avg_roi_match = re.search(r'📈\s*Avg\. ROI:\s*([\d.]+)%', data)
        median_roi_match = re.search(r'📈\s*Median ROI:\s*([\d.]+)%', data)
        profit_match = re.search(r'💰\s*Profit:\s*([-]?[\d.]+)\s*SOL', data)
        avg_hold_match = re.search(r'Avg\. Hold Duration:\s*(\d+)d\s*(\d+)h\s*(\d+)m', data)

        # Parse values (convert to float or int as appropriate)
        winrate = float(winrate_match.group(1)) if winrate_match else None
        roi = float(roi_match.group(1)) if roi_match else None
        avg_roi = float(avg_roi_match.group(1)) if avg_roi_match else None
        median_roi = float(median_roi_match.group(1)) if median_roi_match else None
        profit = float(profit_match.group(1)) if profit_match else None
        avg_hold_duration = (
            int(avg_hold_match.group(1)) * 24 * 60 +  # days to minutes
            int(avg_hold_match.group(2)) * 60 +       # hours to minutes
            int(avg_hold_match.group(3))             # minutes
        ) if avg_hold_match else None

        # Return metrics as a dictionary
        return {
            "winrate": winrate,
            "roi": roi,
            "avg_roi": avg_roi,
            "median_roi": median_roi,
            "profit": profit,
            "avg_hold_duration": avg_hold_duration
        }
    except Exception as e:
        print(f"Error parsing response: {e}")
        return None

def meets_criteria(metrics):
    return (
        metrics["median_roi"] and metrics["median_roi"] >= MIN_MEDIAN_ROI and
        metrics["avg_hold_duration"] and metrics["avg_hold_duration"] >= MIN_HOLD_TIME_MINUTES and
        metrics["winrate"] and metrics["winrate"] >= MIN_WIN_RATE
    )

# Function to push data to Google Sheets
def push_to_google_sheets(winners_data):
    # Authenticate using the service account credentials
    credentials = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_SHEETS_CREDENTIALS, ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive'])
    gc = gspread.authorize(credentials)
    
    # Open the Google Sheet (use the name of your spreadsheet)
    worksheet = gc.open('Wallet Winners').sheet1
    
    # Add winners data to Google Sheets
    for winner in winners_data:
        worksheet.append_row(winner)

# Process wallets from file
async def process_wallets(client):
    with open(WALLET_FILE, 'r') as file:
        wallets = [line.strip() for line in file.readlines()]

    total_wallets = len(wallets)
    processed = 0

    winners_data = []

    with open(RESULTS_FILE, 'w') as results, open(WINNERS_FILE, 'w') as winners:
        for wallet in wallets:
            processed += 1
            print(f'Processing wallet {processed} of {total_wallets}...')
            try:
                async with client.conversation(BOT_USERNAME) as conv:
                    await conv.send_message(f'/check {wallet}')
                    response_text = await wait_for_account_info(conv)

                    if response_text:
                        metrics = analyze_wallet(response_text)
                        if metrics:
                            results.write(f'{wallet} - {metrics}\n')
                            if meets_criteria(metrics):
                                winners.write(f'{wallet} - {metrics}\n')
                                winners_data.append([wallet, metrics['winrate'], metrics['roi'], metrics['avg_roi'], metrics['median_roi'], metrics['profit'], metrics['avg_hold_duration']])
                            print(f"Processed wallet {wallet}: {metrics}")
                        else:
                            print(f"Failed to parse data for wallet: {wallet}")
                    else:
                        print(f"No valid response received for wallet: {wallet}")
            except Exception as e:
                print(f"Error processing wallet {wallet}: {e}")
    
    # Push winners data to Google Sheets
    push_to_google_sheets(winners_data)

# Main entry point
async def main():
    async with TelegramClient('bot_session', API_ID, API_HASH) as client:
        print("Connected to Telegram!")
        await process_wallets(client)

if __name__ == '__main__':
    asyncio.run(main())
