## Telegram Mafia Bot

A lightweight Telegram Mafia game bot built with Python.

### Features
- Lobby: `/newgame`, `/join`, `/leave`
- Start game and role assignment: `/startgame`
- Night actions (Mafia/Doctor/Detective via DM)
- Day voting with inline keyboard: `/votestart`, `/endday`
- Night resolution: `/endnight`
- Status and end: `/status`, `/endgame`

### Security
Do NOT hardcode your bot token. Put it in an environment variable or `.env` file.
If your token was ever shared publicly, regenerate it in BotFather.

### Setup
1. Python 3.10+
2. Install deps:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file with:
   ```
   BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
   ```
4. Run the bot:
   ```bash
   python -m bot.main
   ```

### Notes
- Add the bot to a group and make sure members start a private chat with the bot to receive DM actions.
- This implementation stores state in-memory and will reset on restart.
- For production, add persistence (e.g., Redis/PostgreSQL) and admin controls.
