import requests
import json
from datetime import datetime, timedelta
import time
import logging
import sys
import os
import traceback
from threading import Thread

# -----------------------------
# CONFIGURATION LOGGING
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# -----------------------------
# CONFIG - VARIABLES D'ENVIRONNEMENT
# -----------------------------
import os

# Global monitoring control
MONITORING_ACTIVE = True

# Récupération des wallets depuis les variables d'environnement
WALLETS = {}
for i in range(1, 10):
    wallet_addr = os.getenv(f'WALLET_{i}')
    if wallet_addr and wallet_addr.strip():
        WALLETS[f'Wallet{i}'] = wallet_addr.strip()

if not WALLETS:
    WALLETS = {
        "Victim": "H6T8JytFFJTb6j6vy3Y6xQ8a6m4P7hqd2eKRdRKrp6KY"
    }

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '8202868254:AAGrATiPwQPCqUlMxC-kd0EfamVR8BGBBA8')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '6040703360')
TRACKER_API_KEY = os.getenv('TRACKER_API_KEY', 'a2ff7827-79c6-4a5c-8870-abc6a5c7219b')
SOLANA_RPC = "https://api.mainnet-beta.solana.com"
TRACKER_BASE = "https://data.solanatracker.io"

# Caches par wallet
wallet_caches = {
    wallet_name: {
        'token_cache': {},
        'transaction_cache': {},
        'last_processed_trades': set(),
        'error_count': 0,
        'last_success': None
    }
    for wallet_name in WALLETS.keys()
}

# -----------------------------
# FONCTIONS TELEGRAM INTERACTIVES
# -----------------------------

def send_telegram_message(chat_id, message, parse_mode="HTML"):
    """Envoi de message Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": parse_mode
        }
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            return True
        else:
            logger.error(f"❌ Erreur Telegram: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ Impossible d'envoyer message: {e}")
        return False

def send_telegram_notification(message):
    """Envoi de notification au chat principal"""
    return send_telegram_message(TELEGRAM_CHAT_ID, message)

def check_telegram_commands():
    """Vérifie les commandes Telegram en arrière-plan"""
    last_update_id = 0
    
    while True:
        try:
            if not MONITORING_ACTIVE:
                time.sleep(10)
                continue
                
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            params = {
                'offset': last_update_id + 1,
                'timeout': 20
            }
            
            response = requests.get(url, params=params, timeout=25)
            if response.status_code == 200:
                data = response.json()
                if data['ok'] and data['result']:
                    for update in data['result']:
                        last_update_id = update['update_id']
                        process_telegram_command(update)
            time.sleep(2)
                        
        except Exception as e:
            logger.error(f"❌ Erreur vérification commandes: {e}")
            time.sleep(10)

def process_telegram_command(update):
    """Traite les commandes Telegram"""
    if 'message' not in update:
        return
        
    message = update['message']
    chat_id = message['chat']['id']
    text = message.get('text', '').strip()
    
    # Vérifier que c'est bien vous
    if str(chat_id) != TELEGRAM_CHAT_ID:
        send_telegram_message(chat_id, "🚫 Accès refusé - Unauthorized")
        return
    
    if text.startswith('/'):
        command = text.lower()
        
        if command == '/start' or command == '/help':
            send_help(chat_id)
        elif command == '/status':
            send_status(chat_id)
        elif command == '/stop':
            stop_monitoring(chat_id)
        elif command == '/startmonitor':
            start_monitoring(chat_id)
        elif command == '/wallets':
            list_wallets(chat_id)
        elif command.startswith('/add'):
            add_wallet(chat_id, text)
        elif command.startswith('/remove'):
            remove_wallet(chat_id, text)
        else:
            send_telegram_message(chat_id, "❌ Commande inconnue. Tapez /help pour l'aide")

def send_help(chat_id):
    """Affiche l'aide"""
    help_text = """
🤖 <b>SOLANA WALLET MONITOR - COMMANDES</b>

📊 <b>Statut & Info</b>
/status - Voir le statut du monitoring
/wallets - Lister les wallets surveillés

⚡ <b>Contrôle</b>
/stop - Arrêter le monitoring
/startmonitor - Redémarrer le monitoring

👛 <b>Gestion Wallets</b>
/add [adresse] - Ajouter un wallet
/remove [nom] - Retirer un wallet

❓ <b>Aide</b>
/help - Afficher ce message

<b>Exemples:</b>
/add H6T8JytFFJTb6j6vy3Y6xQ8a6m4P7hqd2eKRdRKrp6KY
/remove Wallet1
"""
    send_telegram_message(chat_id, help_text)

def send_status(chat_id):
    """Envoie le statut actuel"""
    status_msg = f"""
📊 <b>STATUT DU MONITORING</b>

🟢 <b>Status:</b> {'ACTIF' if MONITORING_ACTIVE else 'ARRÊTÉ'}
👛 <b>Wallets surveillés:</b> {len(WALLETS)}
🔄 <b>Dernier check:</b> {datetime.now().strftime('%H:%M:%S')}
💻 <b>Serveur:</b> Render.com

<b>Wallets actifs:</b>
"""
    
    for name, address in WALLETS.items():
        status_msg += f"• {name}: {address[:8]}...{address[-6:]}\n"
    
    status_msg += f"\nTapez /help pour toutes les commandes"
    send_telegram_message(chat_id, status_msg)

def stop_monitoring(chat_id):
    """Arrête le monitoring"""
    global MONITORING_ACTIVE
    MONITORING_ACTIVE = False
    send_telegram_message(chat_id, "🛑 <b>Monitoring arrêté</b>\nLe bot ne vérifiera plus les trades. Tapez /startmonitor pour redémarrer.")

def start_monitoring(chat_id):
    """Redémarre le monitoring"""
    global MONITORING_ACTIVE
    MONITORING_ACTIVE = True
    send_telegram_message(chat_id, "🟢 <b>Monitoring redémarré</b>\nLe bot vérifie maintenant les trades.")

def list_wallets(chat_id):
    """Liste tous les wallets"""
    if not WALLETS:
        send_telegram_message(chat_id, "📭 Aucun wallet configuré")
        return
    
    wallets_msg = "👛 <b>WALLETS SURVEILLÉS</b>\n\n"
    for name, address in WALLETS.items():
        wallets_msg += f"<b>{name}:</b>\n<code>{address}</code>\n\n"
    
    wallets_msg += "Utilisez /add [adresse] pour ajouter un wallet\n"
    wallets_msg += "Utilisez /remove [nom] pour retirer un wallet"
    send_telegram_message(chat_id, wallets_msg)

def add_wallet(chat_id, text):
    """Ajoute un wallet"""
    try:
        parts = text.split(' ', 1)
        if len(parts) < 2:
            send_telegram_message(chat_id, "❌ Format: /add ADRESSE_SOLANA")
            return
        
        new_address = parts[1].strip()
        
        # Validation basique de l'adresse Solana
        if len(new_address) != 44:
            send_telegram_message(chat_id, "❌ Adresse Solana invalide (doit faire 44 caractères)")
            return
        
        # Trouver un nom disponible
        wallet_num = len(WALLETS) + 1
        new_name = f"Wallet{wallet_num}"
        
        WALLETS[new_name] = new_address
        wallet_caches[new_name] = {
            'token_cache': {},
            'transaction_cache': {},
            'last_processed_trades': set(),
            'error_count': 0,
            'last_success': None
        }
        
        send_telegram_message(chat_id, f"✅ <b>Wallet ajouté!</b>\n\n<b>Nom:</b> {new_name}\n<b>Adresse:</b> <code>{new_address}</code>\n\nLe monitoring inclut maintenant ce wallet.")
        
    except Exception as e:
        send_telegram_message(chat_id, f"❌ Erreur lors de l'ajout: {str(e)}")

def remove_wallet(chat_id, text):
    """Retire un wallet"""
    try:
        parts = text.split(' ', 1)
        if len(parts) < 2:
            send_telegram_message(chat_id, "❌ Format: /remove NOM_WALLET\nUtilisez /wallets pour voir les noms")
            return
        
        wallet_name = parts[1].strip()
        
        if wallet_name not in WALLETS:
            send_telegram_message(chat_id, f"❌ Wallet '{wallet_name}' non trouvé. Utilisez /wallets pour voir la liste.")
            return
        
        removed_address = WALLETS[wallet_name]
        del WALLETS[wallet_name]
        del wallet_caches[wallet_name]
        
        send_telegram_message(chat_id, f"✅ <b>Wallet retiré!</b>\n\n<b>Nom:</b> {wallet_name}\n<b>Adresse:</b> <code>{removed_address}</code>\n\nCe wallet n'est plus surveillé.")
        
    except Exception as e:
        send_telegram_message(chat_id, f"❌ Erreur lors de la suppression: {str(e)}")

# -----------------------------
# FONCTIONS DE BASE DU MONITORING
# -----------------------------

def get_sol_price():
    """Récupération du prix SOL"""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd&include_market_cap=true"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            price = data['solana']['usd']
            market_cap = data['solana'].get('usd_market_cap', 0)
            return price, market_cap
    except Exception as e:
        logger.error(f"❌ Erreur prix SOL: {e}")
    return 150.0, 65000000000  # Fallback

def get_token_metadata(token_address, fallback_symbol="UNKNOWN", token_cache=None):
    """Get token metadata"""
    if token_cache is None:
        token_cache = {}
    
    if token_address in token_cache:
        return token_cache[token_address]
    
    # SOL token
    if token_address == "So11111111111111111111111111111111111111112":
        result = {'name': 'Solana', 'symbol': 'SOL', 'decimals': 9}
        token_cache[token_address] = result
        return result
    
    # Try Solana Token List
    try:
        url = "https://cdn.jsdelivr.net/gh/solana-labs/token-list@main/src/tokens/solana.tokenlist.json"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            token_list = response.json()
            for token in token_list['tokens']:
                if token['address'] == token_address:
                    result = {
                        'name': token.get('name', 'Unknown Token'),
                        'symbol': token.get('symbol', fallback_symbol),
                        'decimals': token.get('decimals', 9)
                    }
                    token_cache[token_address] = result
                    return result
    except:
        pass
    
    result = {'name': fallback_symbol, 'symbol': fallback_symbol, 'decimals': 9}
    token_cache[token_address] = result
    return result

def get_token_price(token_address):
    """Get token price from DexScreener"""
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data.get('pairs') and len(data['pairs']) > 0:
                pair = data['pairs'][0]
                return {
                    'price': float(pair.get('priceUsd', 0)),
                    'market_cap': float(pair.get('fdv', 0)),
                    'volume_24h': float(pair.get('volume', {}).get('h24', 0)),
                    'price_change_24h': float(pair.get('priceChange', {}).get('h24', 0))
                }
    except Exception as e:
        logger.error(f"❌ Erreur prix token: {e}")
    
    return {'price': 0, 'market_cap': 0, 'volume_24h': 0, 'price_change_24h': 0}

def get_wallet_trades(wallet_address, wallet_name):
    """Récupération des trades"""
    try:
        headers = {"x-api-key": TRACKER_API_KEY}
        url = f"{TRACKER_BASE}/wallet/{wallet_address}/trades?showMeta=true"
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 401:
            logger.error("🔑 Erreur d'authentification API")
            return []
        elif response.status_code == 429:
            logger.warning("⏳ Rate limit atteint")
            time.sleep(60)
            return []
            
        response.raise_for_status()
        data = response.json()
        return data.get('trades', [])
        
    except Exception as e:
        logger.error(f"❌ Erreur trades {wallet_name}: {e}")
        return []

def get_time_ago(timestamp):
    """Formatage du temps"""
    if not timestamp:
        return "Recent"
    
    now = datetime.now()
    tx_time = datetime.fromtimestamp(timestamp)
    diff = now - tx_time
    
    if diff.days > 0:
        return f"{diff.days}d ago"
    elif diff.seconds >= 3600:
        hours = diff.seconds // 3600
        return f"{hours}h ago"
    elif diff.seconds >= 60:
        minutes = diff.seconds // 60
        return f"{minutes}m ago"
    else:
        return "Just now"

def format_market_cap(value):
    """Format market cap"""
    if value >= 1000000000:
        return f"${value/1000000000:.2f}B"
    elif value >= 1000000:
        return f"${value/1000000:.2f}M"
    elif value >= 1000:
        return f"${value/1000:.2f}K"
    else:
        return f"${value:.2f}" if value > 0 else "-"

def format_price_change(change):
    """Format price change"""
    if change > 0:
        return f"🟢 +{change:.1f}%"
    elif change < 0:
        return f"🔴 {change:.1f}%"
    else:
        return "⚪ 0.0%"

def extract_swap_info(trade, sol_price, sol_market_cap, token_cache=None):
    """Extraction des infos de swap"""
    if token_cache is None:
        token_cache = {}
    
    if not isinstance(trade, dict):
        return None
    
    tx_signature = trade.get('tx', 'Unknown')
    
    from_data = trade.get('from', {})
    from_token = from_data.get('token', {})
    to_data = trade.get('to', {})
    to_token = to_data.get('token', {})
    
    if not from_data or not to_data:
        return None
    
    # Get token addresses and symbols
    from_token_address = from_data.get('address', '')
    to_token_address = to_data.get('address', '')
    from_token_symbol = from_token.get('symbol', 'UNKNOWN')
    to_token_symbol = to_token.get('symbol', 'UNKNOWN')
    
    # Get token metadata
    from_metadata = get_token_metadata(from_token_address, from_token_symbol, token_cache)
    to_metadata = get_token_metadata(to_token_address, to_token_symbol, token_cache)
    
    # Get token prices
    from_price_info = get_token_price(from_token_address)
    to_price_info = get_token_price(to_token_address)
    
    # Determine action
    if from_metadata['symbol'] == "SOL":
        action = "Buy"
        token_traded = to_metadata['name']
        token_symbol = to_metadata['symbol']
        token_address = to_token_address
        amount_traded = to_data.get('amount', 0)
        sol_amount = from_data.get('amount', 0)
        value = sol_amount * sol_price
        market_cap = to_price_info['market_cap']
        token_price = to_price_info['price']
        price_change = to_price_info['price_change_24h']
    else:
        action = "Sell" 
        token_traded = from_metadata['name']
        token_symbol = from_metadata['symbol']
        token_address = from_token_address
        amount_traded = from_data.get('amount', 0)
        sol_amount = to_data.get('amount', 0)
        value = sol_amount * sol_price
        market_cap = from_price_info['market_cap']
        token_price = from_price_info['price']
        price_change = from_price_info['price_change_24h']
    
    return {
        'tx_signature': tx_signature,
        'action': action,
        'token_traded': token_traded,
        'token_symbol': token_symbol,
        'token_address': token_address,
        'amount_traded': amount_traded,
        'value': value,
        'market_cap': market_cap,
        'token_price': token_price,
        'price_change_24h': price_change,
        'sol_amount': sol_amount
    }

def check_new_trades_and_notify(swaps, wallet_name):
    """Vérification des nouveaux trades"""
    wallet_cache = wallet_caches[wallet_name]
    
    new_trades = []
    current_trades = set()
    
    for swap in swaps:
        tx_hash = swap['tx_signature']
        current_trades.add(tx_hash)
        
        if tx_hash not in wallet_cache['last_processed_trades']:
            new_trades.append(swap)
    
    # Send notifications for new trades
    for trade in new_trades:
        send_trade_notification(trade, wallet_name)
    
    # Update processed trades
    wallet_cache['last_processed_trades'] = current_trades
    
    return len(new_trades)

def send_trade_notification(trade, wallet_name):
    """Notification de trade"""
    try:
        action = trade['action']
        token_symbol = trade['token_symbol']
        amount = trade['amount_traded']
        value = trade['value']
        token_price = trade['token_price']
        price_change = trade['price_change_24h']
        tx_hash = trade['tx_signature']
        
        # Get volume data
        token_address = trade['token_address']
        token_data = get_token_price(token_address)
        volume_24h = token_data.get('volume_24h', 0)
        market_cap = trade['market_cap']
        
        if action == "Buy":
            emoji = "🟢"
            action_text = "BOUGHT"
        else:
            emoji = "🔴" 
            action_text = "SOLD"
        
        volume_formatted = format_market_cap(volume_24h)
        market_cap_formatted = format_market_cap(market_cap)
        volume_emoji = "🔥" if volume_24h > 1000000 else "📊"
        
        message = f"""
{emoji} <b>TRADE ALERT - {action_text}</b> {emoji}

👛 <b>Wallet:</b> {wallet_name}
💰 <b>Token:</b> {token_symbol}
📊 <b>Action:</b> {action_text}
🔢 <b>Amount:</b> {amount:,.0f}
💵 <b>Value:</b> ${value:.2f}
🎯 <b>Price:</b> ${token_price:.6f}
📈 <b>24h Change:</b> {format_price_change(price_change)}

{volume_emoji} <b>24h Volume:</b> {volume_formatted}
🏦 <b>Market Cap:</b> {market_cap_formatted}
⏰ <b>Time:</b> {get_time_ago(trade.get('timestamp'))}

🔗 <b>TX:</b> <code>{tx_hash}</code>

<a href="https://solscan.io/tx/{tx_hash}">View on Solscan</a>
<a href="https://dexscreener.com/solana/{token_address}">View on DexScreener</a>
"""
        
        send_telegram_notification(message)
        logger.info(f"📢 Notification: {wallet_name} - {action} {token_symbol}")
        
    except Exception as e:
        logger.error(f"❌ Erreur notification trade: {e}")

# -----------------------------
# FONCTION MANQUANTE - AJOUTÉE ICI
# -----------------------------

def monitor_wallet_safe(wallet_name, wallet_address):
    """Monitoring sécurisé d'un wallet"""
    wallet_cache = wallet_caches[wallet_name]
    
    try:
        logger.info(f"🔍 Checking {wallet_name}...")
        
        # Get data
        sol_price, sol_market_cap = get_sol_price()
        trades = get_wallet_trades(wallet_address, wallet_name)
        
        # Process trades
        swaps = []
        for trade in trades[:8]:  # Limit for performance
            swap = extract_swap_info(trade, sol_price, sol_market_cap, wallet_cache['token_cache'])
            if swap:
                swaps.append(swap)
        
        # Check new trades
        new_trades_count = check_new_trades_and_notify(swaps, wallet_name)
        
        # Update status
        wallet_cache['last_success'] = datetime.now()
        wallet_cache['error_count'] = 0
        
        logger.info(f"✅ {wallet_name}: {len(swaps)} trades, {new_trades_count} new")
        return new_trades_count
        
    except Exception as e:
        wallet_cache['error_count'] += 1
        error_count = wallet_cache['error_count']
        
        logger.error(f"❌ Error {wallet_name} (attempt {error_count}): {e}")
        
        # Alert after 3 errors
        if error_count == 3:
            send_telegram_notification(
                f"🚨 <b>Problem with {wallet_name}</b>\n"
                f"Error: {str(e)[:200]}\n"
                f"3 consecutive errors"
            )
        
        # Pause after 5 errors
        if error_count >= 5:
            logger.error(f"🔴 Too many errors for {wallet_name}, pausing")
            time.sleep(600)
            wallet_cache['error_count'] = 0
        
        return 0

# -----------------------------
# SUPERVISEUR PRINCIPAL
# -----------------------------

def monitor_wallets_supervisor():
    """Superviseur principal avec contrôle Telegram"""
    logger.info("🚀 Starting Interactive Wallet Monitor Supervisor")
    
    consecutive_errors = 0
    max_consecutive_errors = 5
    iteration = 0
    
    while True:
        try:
            if not MONITORING_ACTIVE:
                logger.info("⏸️ Monitoring paused - waiting for /startmonitor")
                time.sleep(30)
                continue
                
            iteration += 1
            logger.info(f"🔄 Monitoring cycle #{iteration}")
            
            total_new_trades = 0
            
            # Monitor each wallet
            for wallet_name, wallet_address in WALLETS.items():
                new_trades = monitor_wallet_safe(wallet_name, wallet_address)
                total_new_trades += new_trades
            
            # Reset error counter
            consecutive_errors = 0
            
            # Status log
            if total_new_trades > 0:
                logger.info(f"📢 {total_new_trades} new trades processed")
            
            # Health check every 30 iterations
            if iteration % 30 == 0:
                health_status = f"💚 Health Check - {len(WALLETS)} wallets, Cycle #{iteration}"
                logger.info(health_status)
            
            # Wait between cycles
            time.sleep(45)
            
        except Exception as e:
            consecutive_errors += 1
            logger.critical(f"💥 SUPERVISOR ERROR (attempt {consecutive_errors}): {e}")
            logger.critical(traceback.format_exc())
            
            if consecutive_errors == 1:
                send_telegram_notification(
                    f"💥 <b>Supervisor Error</b>\n"
                    f"Error: {str(e)[:300]}\n"
                    f"Attempting restart..."
                )
            
            if consecutive_errors >= max_consecutive_errors:
                logger.critical("🔴 FORCED STOP - Too many errors")
                send_telegram_notification(
                    "🔴 <b>FORCED STOP</b>\n"
                    f"{max_consecutive_errors} consecutive errors\n"
                    "Manual restart required"
                )
                sys.exit(1)
            
            wait_time = min(300, 30 * consecutive_errors)
            logger.info(f"⏳ Waiting {wait_time}s before restart...")
            time.sleep(wait_time)

def render_keep_alive():
    """Keep Render service active"""
    while True:
        try:
            logger.info("💚 Render Keep-Alive - Service is running")
            time.sleep(300)
        except Exception as e:
            logger.error(f"❌ Keep-alive error: {e}")

def main():
    """Point d'entrée principal avec interaction Telegram"""
    try:
        logger.info("🎯 Initializing Interactive Solana Wallet Monitor")
        
        # Start keep-alive for Render
        keep_alive_thread = Thread(target=render_keep_alive, daemon=True)
        keep_alive_thread.start()
        
        # Start Telegram command listener
        telegram_thread = Thread(target=check_telegram_commands, daemon=True)
        telegram_thread.start()
        
        # Startup notification
        wallet_list = "\n".join([f"• {name}: {addr[:8]}...{addr[-6:]}" for name, addr in WALLETS.items()])
        send_telegram_notification(
            f"🚀 <b>Solana Wallet Monitor Started</b>\n"
            f"👛 Tracking {len(WALLETS)} wallets\n"
            f"📋 {wallet_list}\n"
            f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"☁️ Platform: Render.com\n\n"
            f"<b>🤖 BOT INTERACTIF ACTIVÉ</b>\n"
            f"Tapez /help pour voir toutes les commandes disponibles\n"
            f"Tapez /status pour voir le statut actuel"
        )
        
        # Start monitoring
        monitor_wallets_supervisor()
        
    except KeyboardInterrupt:
        logger.info("🛑 Manual stop")
        send_telegram_notification("🛑 Monitoring stopped manually")
    except Exception as e:
        logger.critical(f"💥 FATAL ERROR: {e}")
        logger.critical(traceback.format_exc())
        send_telegram_notification(
            f"💀 <b>FATAL ERROR</b>\n"
            f"Monitoring crashed:\n"
            f"{str(e)[:400]}"
        )
        sys.exit(1)

if __name__ == "__main__":
    main()
