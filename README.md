 JavaScript & Endpoint Monitor

A Python script to monitor JavaScript files for changes, discover new API endpoints, and send detailed alerts to Discord. This is a great tool for bug bounty hunters and developers who want to stay on top of web application changes.

## Key Features

* **JS Code Diffing**: Tracks changes in JavaScript files and provides a `diff` of what was added or removed.
* **Endpoint Discovery**: Automatically parses JS files to find new and previously unknown API endpoints.
* **Discord Alerts**: Sends instant notifications to a Discord channel with change summaries, code snippets, and discovered endpoints.
* **Local Archiving**: Saves a full history of JS file changes and a log of all discovered endpoints.

## Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/bogbounty/Javascript-monitoring.git
    cd Javascript-monitoring
    ```

2.  **Install dependencies:**
    ```bash
    pip install requests discord-webhook
    ```

3.  **Configure the script:**
    * Open `bogbounty-javascript-mon.py` and set your `WEBHOOK_URL` to your Discord webhook.
    * Create a `targets.txt` file in the same directory. Add the direct URLs to the JavaScript files you want to monitor, one URL per line.

    **Example `targets.txt`:**
    ```
    https://example.com/assets/app.js
    https://anothersite.com/main.chunk.js
    ```

## Usage

Simply run the script from your terminal:

```bash
python bogbounty-javascript-mon.py
```

The script will start monitoring the files listed in `targets.txt`.

## How it Works

* The script periodically fetches the content of each URL in `targets.txt`.
* It compares the hash of the new content with the stored hash to detect changes.
* If a change is detected, it saves a diff log in the `js_changes` directory and sends a Discord alert.
* It also scans all JS content for potential endpoints and logs any new discoveries in `discovered_endpoints.txt`, also triggering a Discord alert.

## Updates 

+ Fixed code logic and indentation
+ Added realistic User-Agent 
