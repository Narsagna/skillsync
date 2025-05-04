import os
import requests
import time
import random
import pandas as pd
import argparse
import json
from tqdm import tqdm
from collections import deque
from datetime import datetime

# Constants adjusted for your project structure
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
METADATA_FILE = os.path.join(BASE_DIR, "pr_metadata.json")
LOG_FILE = os.path.join(BASE_DIR, "download_log.txt")
TOKEN_STATUS_FILE = os.path.join(BASE_DIR, "token_status.json")
ALL_PATCHES_FILE = os.path.join(BASE_DIR, "all_patches.txt")
PATCH_BASE_URL = "https://patch-diff.githubusercontent.com/raw/facebook/react/pull/{pr_number}.patch"

# Base delay in seconds
BASE_DELAY = 2.0
# Maximum delay in seconds
MAX_DELAY = 120
# Maximum retries per PR
MAX_RETRIES = 5

class TokenManager:
    """Manages multiple GitHub tokens with rotation and rate limit tracking"""
    
    def __init__(self, tokens):
        self.tokens = deque(tokens)
        self.token_status = {}
        self.current_token = None
        self.load_token_status()
        
    def load_token_status(self):
        """Load token status from file if available"""
        if os.path.exists(TOKEN_STATUS_FILE):
            try:
                with open(TOKEN_STATUS_FILE, 'r') as f:
                    self.token_status = json.load(f)
                log_message("Loaded token status from file")
            except Exception as e:
                log_message(f"Error loading token status: {e}")
                self._initialize_token_status()
        else:
            self._initialize_token_status()
    
    def _initialize_token_status(self):
        """Initialize token status for all tokens"""
        self.token_status = {}
        for token in self.tokens:
            self.token_status[token] = {
                "reset_time": datetime.now().timestamp(),
                "remaining": 5000,  # Default GitHub rate limit
                "backoff_until": 0,
                "consecutive_errors": 0
            }
    
    def save_token_status(self):
        """Save token status to file"""
        with open(TOKEN_STATUS_FILE, 'w') as f:
            json.dump(self.token_status, f, indent=2)
    
    def get_next_token(self):
        """Get the next available token with the highest remaining rate limit"""
        now = datetime.now().timestamp()
        
        # Reset any tokens that have passed their reset time
        for token, status in self.token_status.items():
            if status["reset_time"] < now:
                status["remaining"] = 5000
                status["reset_time"] = now + 3600  # Assume 1 hour reset
                log_message(f"Token {token[:7]}... rate limit reset")
            
            # Clear backoff if time has passed
            if status["backoff_until"] < now:
                status["backoff_until"] = 0
        
        # Sort tokens by remaining requests and backoff status
        available_tokens = []
        for token in self.tokens:
            status = self.token_status[token]
            # Skip tokens in backoff
            if status["backoff_until"] > now:
                continue
            # Skip tokens with no remaining requests
            if status["remaining"] <= 10:  # Keep a small buffer
                continue
            available_tokens.append((token, status["remaining"]))
        
        # If we have available tokens, use the one with most remaining requests
        if available_tokens:
            available_tokens.sort(key=lambda x: x[1], reverse=True)
            self.current_token = available_tokens[0][0]
        else:
            # Find token with earliest reset or backoff end
            next_available = sorted(
                [(t, min(s["reset_time"], s["backoff_until"] or float('inf'))) 
                 for t, s in self.token_status.items()],
                key=lambda x: x[1]
            )[0]
            
            self.current_token = next_available[0]
            wait_time = max(0, next_available[1] - now)
            
            if wait_time > 0:
                log_message(f"All tokens are rate limited. Waiting {wait_time:.2f} seconds for next available token.")
                time.sleep(wait_time)
        
        # Rotate token to the end of the queue for round-robin effect
        self.tokens.remove(self.current_token)
        self.tokens.append(self.current_token)
        
        return self.current_token
    
    def update_token_status(self, response=None, error=None):
        """Update token status based on API response or error"""
        if not self.current_token:
            return
        
        status = self.token_status[self.current_token]
        
        if error:
            status["consecutive_errors"] += 1
            
            # If too many consecutive errors, put token in backoff
            if status["consecutive_errors"] >= 3:
                backoff_time = min(30 * (2 ** (status["consecutive_errors"] - 3)), 3600)
                status["backoff_until"] = datetime.now().timestamp() + backoff_time
                log_message(f"Token {self.current_token[:7]}... put in backoff for {backoff_time} seconds after consecutive errors")
        
        elif response:
            status["consecutive_errors"] = 0
            
            # Update rate limit info if headers are present
            if 'X-RateLimit-Remaining' in response.headers:
                status["remaining"] = int(response.headers.get('X-RateLimit-Remaining', 0))
                
            if 'X-RateLimit-Reset' in response.headers:
                status["reset_time"] = int(response.headers.get('X-RateLimit-Reset', 0))
                
            # Handle secondary rate limits
            if response.status_code == 429 or "rate limit" in response.text.lower():
                retry_after = int(response.headers.get('Retry-After', 60))
                status["backoff_until"] = datetime.now().timestamp() + retry_after
                log_message(f"Token {self.current_token[:7]}... hit rate limit, backing off for {retry_after} seconds")
        
        # Save status to file
        self.save_token_status()


def log_message(message):
    """Log a message to the log file and print it"""
    print(message)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}\n")

def load_pr_numbers(input_file):
    """Load PR numbers from a CSV file exported from BigQuery"""
    input_path = os.path.join(BASE_DIR, input_file)
    df = pd.read_csv(input_path)
    return df["pr_number"].tolist(), df.to_dict('records')

def save_metadata(pr_data):
    """Save PR metadata to a JSON file"""
    with open(METADATA_FILE, "w", encoding="utf-8") as f:
        json.dump(pr_data, f, indent=2)

def check_pr_already_downloaded(pr_number):
    """Check if a PR has already been downloaded"""
    try:
        with open(ALL_PATCHES_FILE, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            return f"===== PR #{pr_number} =====" in content
    except FileNotFoundError:
        # File doesn't exist yet
        return False

def download_patch(pr_number, token_manager):
    """Download a patch file for a PR number and append to all_patches.txt"""
    # Check if PR is already in the file
    if check_pr_already_downloaded(pr_number):
        return True, "Already downloaded"
    
    url = PATCH_BASE_URL.format(pr_number=pr_number)
    delay = BASE_DELAY
    retries = 0
    
    while retries < MAX_RETRIES:
        # Get the next available token
        token = token_manager.get_next_token()
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Authorization": f"token {token}"
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            token_manager.update_token_status(response=response)
            
            if response.status_code == 200:
                # Append to all_patches.txt
                with open(ALL_PATCHES_FILE, "a", encoding="utf-8") as f:
                    f.write(f"\n\n===== PR #{pr_number} =====\n")
                    f.write(response.text)
                    f.write(f"\n===== END PR #{pr_number} =====\n")
                return True, "Success"
                
            elif response.status_code == 429 or "rate limit" in response.text.lower():
                retries += 1
                # Token manager already applied backoff based on response
                continue
                
            elif response.status_code == 404:
                return False, "PR not found"
                
            else:
                log_message(f"Error for PR #{pr_number}: Status {response.status_code}")
                token_manager.update_token_status(error=f"Status {response.status_code}")
                retries += 1
                wait_time = min(delay * (2 ** retries) + random.uniform(0, 1), MAX_DELAY)
                time.sleep(wait_time)
                
        except Exception as e:
            log_message(f"Exception for PR #{pr_number}: {str(e)}")
            token_manager.update_token_status(error=str(e))
            retries += 1
            wait_time = min(delay * (2 ** retries) + random.uniform(0, 1), MAX_DELAY)
            time.sleep(wait_time)
            
    return False, f"Failed after {MAX_RETRIES} retries"

def get_downloaded_prs():
    """Get a list of PR numbers that have already been downloaded"""
    downloaded_prs = set()
    try:
        with open(ALL_PATCHES_FILE, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            import re
            # Find all PR numbers in the file
            pr_markers = re.findall(r"===== PR #(\d+) =====", content)
            for pr in pr_markers:
                downloaded_prs.add(int(pr))
    except FileNotFoundError:
        # File doesn't exist yet
        pass
    return downloaded_prs

def main():
    parser = argparse.ArgumentParser(description="Download PR patches from GitHub with token rotation")
    parser.add_argument("--input", required=True, help="CSV file with PR numbers from BigQuery")
    parser.add_argument("--batch-size", type=int, default=10, help="Number of PRs to process before taking a longer break")
    parser.add_argument("--batch-delay", type=int, default=30, help="Seconds to wait between batches")
    parser.add_argument("--tokens", nargs="+", help="List of GitHub tokens to use")
    parser.add_argument("--tokens-file", help="File containing GitHub tokens (one per line)")
    parser.add_argument("--resume", action="store_true", help="Resume from last successfully processed PR")
    args = parser.parse_args()
    
    # Collect tokens from arguments or file
    tokens = []
    if args.tokens:
        tokens.extend(args.tokens)
    
    if args.tokens_file:
        tokens_file_path = os.path.join(BASE_DIR, args.tokens_file)
        if os.path.exists(tokens_file_path):
            with open(tokens_file_path, 'r') as f:
                tokens.extend([line.strip() for line in f if line.strip()])
    
    # Also check environment variable
    if os.environ.get("GITHUB_TOKENS"):
        env_tokens = os.environ.get("GITHUB_TOKENS").split(',')
        tokens.extend([t.strip() for t in env_tokens if t.strip()])
    
    # Deduplicate tokens
    tokens = list(set(tokens))
    
    if not tokens:
        log_message("No GitHub tokens provided. Using unauthenticated requests (highly rate limited).")
        tokens = [""]  # Empty token for unauthenticated requests
    
    # Initialize token manager
    token_manager = TokenManager(tokens)
    log_message(f"Using {len(tokens)} GitHub tokens for requests")
    
    # Initialize log file if not resuming
    if not args.resume:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - Starting download of React PR patches\n")
    else:
        log_message("Resuming previous download session")
    
    # Load PR numbers and metadata from BigQuery export
    pr_numbers, pr_data = load_pr_numbers(args.input)
    log_message(f"Loaded {len(pr_numbers)} PR numbers from {args.input}")
    
    # Save metadata
    save_metadata(pr_data)
    
    # Find start position if resuming
    if args.resume:
        downloaded_prs = get_downloaded_prs()
        if downloaded_prs:
            # Filter the list to only include PRs that haven't been downloaded yet
            pr_numbers = [pr for pr in pr_numbers if int(pr) not in downloaded_prs]
            log_message(f"Resuming: {len(downloaded_prs)} PRs already downloaded, {len(pr_numbers)} remaining")
    
    # Stats
    total = len(pr_numbers)
    successful = 0
    failed = 0
    
    # Process PRs 
    for i, pr_number in enumerate(tqdm(pr_numbers)):
        # Add jitter to delay
        jitter = random.uniform(-0.3, 0.3) * BASE_DELAY
        current_delay = max(0.5, BASE_DELAY + jitter)
        
        # Download patch
        success, message = download_patch(pr_number, token_manager)
        
        if success:
            successful += 1
            if i % 10 == 0:  # Only log every 10th success to reduce noise
                log_message(f"PR #{pr_number}: {message}")
        else:
            failed += 1
            log_message(f"PR #{pr_number}: {message}")
        
        # Take longer break between batches
        if (i + 1) % args.batch_size == 0:
            batch_delay = args.batch_delay + random.uniform(-5, 5)
            log_message(f"Completed batch {(i + 1) // args.batch_size} of {total // args.batch_size + 1}. " 
                        f"Progress: {i+1}/{total} ({((i+1)/total)*100:.1f}%). "
                        f"Taking a {batch_delay:.2f} second break...")
            time.sleep(batch_delay)
        else:
            time.sleep(current_delay)
    
    log_message(f"Download complete: {successful} successful, {failed} failed")

if __name__ == "__main__":
    main()