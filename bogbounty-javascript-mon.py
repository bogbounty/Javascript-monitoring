import requests
import time
import os
import hashlib
from difflib import unified_diff # For showing blocks of code changes
from discord_webhook import DiscordWebhook, DiscordEmbed
import re # For endpoint discovery
# import json # Not strictly needed if response.json() is used, but good for reference

# --- Configuration ---
TARGET_FILE = "targets.txt"
OUTPUT_DIR = "js_changes"
# Your webhook URL is correctly placed here:
WEBHOOK_URL = "" 
CHECK_INTERVAL_SECONDS = 2600 # As per your last provided script
USER_AGENT = "JSChangeMonitor/1.0 (BugBounty)"
MAX_DIFF_LINES_IN_DISCORD = 15
MAX_DISCORD_FIELD_LENGTH = 1000
# --- New Configuration for Endpoint Discovery ---
ENDPOINT_LOG_FILE = "discovered_endpoints.txt"
# Regex to find potential endpoints (quoted strings starting with / followed by at least 2 path-like characters)
ENDPOINT_REGEX = re.compile(r"""
    (['"`])    # Start quote (capture group 1)
    (          # Start path group (capture group 2)
        /      # Literal slash - ensures it starts like /something
        [a-zA-Z0-9_./-]{2,} # At least 2 path-like characters (alphanumeric, _, ., /, -)
    )
    \1         # End quote (matching the start quote)
""", re.VERBOSE)
# --- Rate Limiting Configuration for Discord ---
PROACTIVE_DISCORD_DELAY_SECONDS = 8.5  # Wait 8.5 seconds before attempting each Discord message
MAX_DISCORD_RETRIES = 3              # Max number of retries if a message fails
DISCORD_RETRY_BUFFER_SECONDS = 0.5   # Extra buffer to add to Discord's retry_after
# --- Helper Functions ---
def read_targets(filename=TARGET_FILE):
    if not os.path.exists(filename):
        print(f"❌ Error: Target file '{filename}' not found. Please create it.")
        return []
    with open(filename, 'r', encoding='utf-8') as f:
        targets = [line.strip() for line in f if line.strip() and line.startswith(('http://', 'https://'))]
    if not targets:
        print(f"ℹ️ No valid URLs found in '{filename}'. Make sure they start with http:// or https://.")
    return targets
def fetch_js_content(url):
    headers = {'User-Agent': USER_AGENT}
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        try:
            content = response.content.decode('utf-8')
        except UnicodeDecodeError:
            content = response.text # Let requests handle encoding if utf-8 fails
        return content
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Error fetching {url}: {e}")
        return None
def get_content_hash(content):
    return hashlib.md5(content.encode('utf-8', 'ignore')).hexdigest()
# --- Endpoint Discovery Functions ---
def load_known_endpoints(filename=ENDPOINT_LOG_FILE):
    known_endpoints = set()
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                if "(Source: " in line: # Ensure we're loading lines that are actual endpoint logs
                    known_endpoints.add(line.strip())
    return known_endpoints
def extract_and_log_endpoints(js_content, js_url, known_endpoints_log_lines, endpoint_log_file=ENDPOINT_LOG_FILE):
    found_paths = set()
    newly_discovered_for_alert = []
    for match in ENDPOINT_REGEX.finditer(js_content):
        path = match.group(2).strip()
        if len(path) > 1 and path.endswith('/'):
            path = path[:-1]
        if len(path) > 0 :
            found_paths.add(path)
    if not found_paths:
    new_entries_for_file = []
    for path in sorted(list(found_paths)):
        log_entry = f"{path} (Source: {js_url})"
        if log_entry not in known_endpoints_log_lines:
            new_entries_for_file.append(log_entry)
            newly_discovered_for_alert.append(path)
            known_endpoints_log_lines.add(log_entry)
    if new_entries_for_file:
        with open(endpoint_log_file, 'a', encoding='utf-8') as f:
            for entry in new_entries_for_file:
                f.write(entry + "\n")
        print(f"🔍 Discovered {len(new_entries_for_file)} new endpoint(s) in {js_url}. Saved to {endpoint_log_file}")
    return newly_discovered_for_alert
# --- Discord & File Saving Functions ---
def send_discord_alert(webhook_url, url, filename, old_hash, new_hash, diff_output, new_endpoints_found=None):
    # Access global rate limiting constants
    # global PROACTIVE_DISCORD_DELAY_SECONDS, MAX_DISCORD_RETRIES, DISCORD_RETRY_BUFFER_SECONDS 
    # No need for 'global' keyword if they are module-level constants and not reassigned in this function
    if not webhook_url or "YOUR_DISCORD_WEBHOOK_URL" in webhook_url: # Check for placeholder
        print("ℹ️ Discord webhook URL not configured or is placeholder. Skipping notification.")
        return
    # Proactive delay to avoid hitting rate limits too quickly
    time.sleep(PROACTIVE_DISCORD_DELAY_SECONDS)
    webhook_obj = DiscordWebhook(url=webhook_url) # Create new object for each alert
    embed_title = "🚨 JS Change Detected!"
    alert_description = f"Changes detected in:\n**{url}**"
    alert_color = "0xff0000"  # Red for changes
    if new_endpoints_found and not diff_output and not old_hash : # Only new endpoints, no JS change (or new file)
        embed_title="✨ New Endpoints Discovered! ✨"
        alert_description=f"New potential endpoints found in:\n**{url}**\n(JS content itself unchanged or new to tracking)"
        alert_color="0x00ff00" # Green for new endpoints only
    elif new_endpoints_found and (diff_output or old_hash): # JS changed AND new endpoints
        embed_title = "🚨 JS Change & New Endpoints! 🚨"
    embed = DiscordEmbed(
        title=embed_title,
        description=alert_description,
        color=alert_color
    if old_hash : # Indicates a JS change occurred (not a new file first seen with only endpoints)
        embed.add_embed_field(name="Old Hash (MD5)", value=f"`{old_hash}`", inline=True) # old_hash will not be None if JS changed
        embed.add_embed_field(name="New Hash (MD5)", value=f"`{new_hash}`", inline=True)
    elif not old_hash and new_hash and not diff_output and new_endpoints_found: # New file, no diff, but new endpoints
         embed.add_embed_field(name="File Hash (MD5)", value=f"`{new_hash}`", inline=True)
    if filename: # Log file for JS changes
        embed.add_embed_field(name="JS Change Log File", value=f"`{filename}`", inline=False)
    if diff_output: # Snippet of JS code changes
        diff_lines = diff_output.splitlines()
        if len(diff_lines) > 2: # Remove unified_diff header
             diff_lines = diff_lines[2:]
        diff_snippet = "\n".join(diff_lines[:MAX_DIFF_LINES_IN_DISCORD])
        if len(diff_lines) > MAX_DIFF_LINES_IN_DISCORD:
            diff_snippet += f"\n... (and {len(diff_lines) - MAX_DIFF_LINES_IN_DISCORD} more lines)"
        if len(diff_snippet) > MAX_DISCORD_FIELD_LENGTH:
            diff_snippet = diff_snippet[:MAX_DISCORD_FIELD_LENGTH - 20] + "\n... (truncated)"
        if diff_snippet.strip():
            embed.add_embed_field(name="Code Changes Snippet (Diff):", value=f"```diff\n{diff_snippet}\n```", inline=False)
    if new_endpoints_found:
        endpoints_snippet = "\n".join([f"- `{ep}`" for ep in new_endpoints_found[:10]])
        if len(new_endpoints_found) > 10:
            endpoints_snippet += f"\n... (and {len(new_endpoints_found) - 10} more)"
        embed.add_embed_field(name="Newly Discovered Endpoints:", value=endpoints_snippet, inline=False)
        embed.add_embed_field(name="Full Endpoint Log", value=f"`{ENDPOINT_LOG_FILE}`", inline=False)
    embed.set_footer(text="JS & Endpoint Monitor")
    embed.set_timestamp()
    webhook_obj.add_embed(embed)
    current_retry = 0
    while current_retry <= MAX_DISCORD_RETRIES:
            if current_retry > 0:
                # This sleep is for retries not related to explicit 429 retry_after
                time.sleep((2 ** current_retry) + DISCORD_RETRY_BUFFER_SECONDS) # Basic exponential backoff
            responses = webhook_obj.execute()
            # execute() returns a list of response objects if successful, or raises an exception for some HTTP errors
            # For simplicity, assume a single response or handle it if it's a list from multiple webhooks (not our case)
            response = responses[0] if isinstance(responses, list) and responses else responses
            
            # Check if response is not None and has status_code (it should be a requests.Response object)
            if response and hasattr(response, 'status_code'):
                if response.status_code in [200, 204]:  # Success
                    print(f"✔️ Discord notification sent for {url}")
                    return
                elif response.status_code == 429:  # Rate limited
                    try:
                        response_data = response.json()
                        retry_after = float(response_data.get("retry_after", 1.0))
                        is_global = response_data.get("global", False)
                        wait_time = retry_after + DISCORD_RETRY_BUFFER_SECONDS
                        
                        print(f"⚠️ Discord rate limit hit for {url}. Message: '{response_data.get('message', 'N/A')}'. Waiting {wait_time:.2f}s. Global: {is_global}. Retrying ({current_retry + 1}/{MAX_DISCORD_RETRIES})...")
                        time.sleep(wait_time)
                        current_retry += 1
                        continue # Go to next iteration of while loop to retry
                    except ValueError: # JSON decoding error or float conversion error
                        print(f"⚠️ Error parsing rate limit response for {url}. Waiting 5s before retry {current_retry + 1}/{MAX_DISCORD_RETRIES}.")
                        time.sleep(5 + DISCORD_RETRY_BUFFER_SECONDS)
                        continue
                    except Exception as e_parse: # Catch any other error during parsing retry_after
                        print(f"⚠️ Unexpected error parsing rate limit data for {url}: {e_parse}. Waiting 5s before retry {current_retry + 1}/{MAX_DISCORD_RETRIES}.")
                        current_retry +=1
                else:  # Other webhook HTTP error
                    error_content = response.content.decode('utf-8') if response.content else 'No content'
                    print(f"⚠️ Discord webhook failed for {url} with status code {response.status_code}: {error_content}")
                    return  # Don't retry on other non-429 persistent errors
            else: # Response object was not as expected (e.g. None, or not a requests.Response)
                print(f"⚠️ Received an unexpected response object type when sending Discord notification for {url}. Retrying ({current_retry + 1}/{MAX_DISCORD_RETRIES})...")
                current_retry += 1
                continue
        except requests.exceptions.RequestException as e:  # Catch network errors from requests library
            print(f"⚠️ Network error sending Discord notification for {url}: {e}. Retrying ({current_retry + 1}/{MAX_DISCORD_RETRIES})...")
            current_retry += 1
            # The while loop's own backoff will apply if current_retry > 0
        
        except Exception as e_general: # Catch any other unexpected errors
            print(f"⚠️ Unexpected error during Discord notification for {url}: {e_general}")
            # import traceback # Uncomment for debugging
            # traceback.print_exc() # Uncomment for debugging
            return # Stop on other unexpected errors
    if current_retry > MAX_DISCORD_RETRIES:
        print(f"❌ Failed to send Discord notification for {url} after {MAX_DISCORD_RETRIES} retries.")
def save_changes(url, old_content, new_content, output_dir=OUTPUT_DIR):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    scheme_removed = url.split("://", 1)[-1]
    filename_prefix = scheme_removed.replace("/", "_").replace("?", "_").replace("&", "_") \
                                    .replace(":", "_").replace("|", "_").replace("<", "_") \
                                    .replace(">", "_").replace("\\", "_").replace("*", "_") \
                                    .replace("\"", "_")
    max_base_len = 150
    if len(filename_prefix) > max_base_len:
        filename_prefix = filename_prefix[:max_base_len // 2] + "..." + filename_prefix[-(max_base_len // 2):]
    
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    output_filename_base = f"{filename_prefix}_{timestamp}.txt"
    output_filename = os.path.join(output_dir, output_filename_base)
    if len(output_filename) > 250: # Check full path length
        # Further shorten filename_prefix if full path is too long
        available_len_for_prefix = 250 - len(os.path.join(output_dir, f"_{timestamp}.txt")) -5 # -5 for safety/ellipsis
        if available_len_for_prefix < 20 : available_len_for_prefix = 20 # minimum sensible prefix
        filename_prefix_shortened = filename_prefix[:available_len_for_prefix//2] + "..." + filename_prefix[-(available_len_for_prefix//2):]
        output_filename = os.path.join(output_dir, f"{filename_prefix_shortened}_{timestamp}.txt")
    diff_lines_generator = unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile='old_version',
        tofile='new_version',
        lineterm='',
        n=3
    diff_string = "".join(list(diff_lines_generator))
    added_lines_only = []
    if diff_string:
        for line in diff_string.splitlines():
            if line.startswith('+') and not line.startswith('+++'):
                added_lines_only.append(line[1:])
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(f"Change detected for URL: {url}\n")
        f.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Old Hash (MD5): {get_content_hash(old_content)}\n")
        f.write(f"New Hash (MD5): {get_content_hash(new_content)}\n")
        f.write("\n" + "="*30 + " FULL UNIFIED DIFF (Code Blocks) " + "="*30 + "\n")
        if diff_string:
            f.write(diff_string)
        else:
            f.write("No textual differences found by diff utility.\n")
        if added_lines_only:
            f.write("\n\n" + "="*33 + " ADDED LINES ONLY " + "="*33 + "\n")
            for line in added_lines_only:
                f.write(line + "\n")
            f.write("No lines were explicitly added according to the diff.\n")
        f.write("\n\n" + "="*34 + " OLD CONTENT " + "="*35 + "\n")
        f.write(old_content)
        f.write("\n\n" + "="*34 + " NEW CONTENT " + "="*35 + "\n")
        f.write(new_content)
    print(f"💾 JS changes saved to: {output_filename}")
    return output_filename, diff_string
# --- Main Logic ---
def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"📁 Created output directory: {OUTPUT_DIR}")
    known_js_data = {}
    known_discovered_endpoints_log_lines = load_known_endpoints(ENDPOINT_LOG_FILE)
    print(f"ℹ️ Loaded {len(known_discovered_endpoints_log_lines)} known endpoint log lines from {ENDPOINT_LOG_FILE}")
    first_run_cycle = True
    print("🚀 JS & Endpoint Monitor Started...")
    print(f"🕒 Checking every {CHECK_INTERVAL_SECONDS // 60} minutes ({CHECK_INTERVAL_SECONDS}s).") # Clarified output
    if WEBHOOK_URL and "YOUR_DISCORD_WEBHOOK_URL" not in WEBHOOK_URL and "discord.com/api/webhooks" in WEBHOOK_URL :
        print(f"🔔 Discord webhook configured. Alerts will be sent.")
    else:
        print("🔔 WARNING: Discord webhook URL not properly configured or is placeholder. Alerts will only be in console.")
    while True:
        targets = read_targets()
        if not targets:
            print("⏳ No targets in 'targets.txt'. Waiting for next check...")
            time.sleep(CHECK_INTERVAL_SECONDS)
            continue
        if first_run_cycle:
            print(f"\n🔍 Initial scan of {len(targets)} target(s) for JS content and endpoints...")
        for url in targets:
            print(f"🔄 Processing: {url}")
            current_content = fetch_js_content(url)
            if current_content is None:
            current_hash = get_content_hash(current_content)
            newly_found_endpoints_for_this_file = extract_and_log_endpoints(current_content, url, known_discovered_endpoints_log_lines)
            # Determine alert type
            log_filename_for_alert = None
            diff_for_alert_content = None
            old_hash_for_alert = None # Default to None for new files
            if url not in known_js_data: # New JS file being tracked for the first time
                known_js_data[url] = {"hash": current_hash, "content": current_content}
                print(f"📝 Stored initial JS version for: {url} (Hash: {current_hash})")
                # For a brand new file, we only alert if new endpoints are found.
                # There's no "change" in JS content to report yet.
                if newly_found_endpoints_for_this_file:
                     send_discord_alert(WEBHOOK_URL, url, None, None, current_hash, None, new_endpoints_found=newly_found_endpoints_for_this_file)
            elif known_js_data[url]["hash"] != current_hash: # Existing URL, content has changed
                print(f"💥 JS CHANGE DETECTED: {url}")
                old_content = known_js_data[url]["content"]
                old_hash_for_alert = known_js_data[url]["hash"]
                log_filename_for_alert, diff_for_alert_content = save_changes(url, old_content, current_content)
                # Send combined alert for JS change and any new endpoints found in the new version
                send_discord_alert(WEBHOOK_URL, url, log_filename_for_alert, old_hash_for_alert, current_hash, diff_for_alert_content, new_endpoints_found=newly_found_endpoints_for_this_file if newly_found_endpoints_for_this_file else None)
            else: # JS content hash is the same as known
                if first_run_cycle:
                     print(f"✔️ No JS changes for: {url} (Hash: {current_hash})")
                # If content is same, but we found endpoints NOT previously logged globally (e.g. script restarted)
                # and it's not the very first scan cycle (where everything is "new")
                if newly_found_endpoints_for_this_file and not first_run_cycle:
                    send_discord_alert(WEBHOOK_URL, url, None, current_hash, current_hash, None, new_endpoints_found=newly_found_endpoints_for_this_file)
            print("\n✅ Initial scan cycle complete. Monitoring for subsequent changes and new endpoints...")
            first_run_cycle = False
        print(f"\n😴 Sleeping for {CHECK_INTERVAL_SECONDS // 60} minutes ({CHECK_INTERVAL_SECONDS} seconds)...\n")
        time.sleep(CHECK_INTERVAL_SECONDS)
if __name__ == "__main__":
        main()
    except KeyboardInterrupt:
        print("\n🛑 JS & Endpoint Monitor Stopped Manually.")
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
