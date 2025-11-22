import re
import hashlib
import requests
from info import *
from utils import *
from pyrogram import Client, filters
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

# Advanced Language Mapping
LANG_MAP = {
    "hi": "Hindi", "hin": "Hindi",
    "en": "English", "eng": "English",
    "bn": "Bengali", "ban": "Bengali", "ben": "Bengali",
    "tm": "Tamil", "tam": "Tamil",
    "te": "Telugu", "tel": "Telugu",
    "ml": "Malayalam", "mal": "Malayalam",
    "kn": "Kannada", "kan": "Kannada",
    "mr": "Marathi", "pa": "Punjabi",
    "gu": "Gujarati", "ko": "Korean",
    "ja": "Japanese", "es": "Spanish",
    "fr": "French", "ur": "Urdu",
    "dual": "Dual Audio", "multi": "Multi Audio"
}

# Global Storage
notified_movies = set()
user_reactions = {}
reaction_counts = {}
movie_slugs = {}  # New: Stores long file names mapped to short IDs

media_filter = filters.document | filters.video | filters.audio

@Client.on_message(filters.chat(CHANNELS) & media_filter)
async def media(bot, message):
    """Media Handler"""
    for file_type in ("document", "video", "audio"):
        media = getattr(message, file_type, None)
        if media is not None:
            break
    else:
        return
    media.file_type = file_type
    media.caption = message.caption
    success, silentxbotz = await save_file(bot, media)
    try:  
        if success and silentxbotz == 1 and await get_status(bot.me.id):            
            await send_movie_update(bot, file_name=media.file_name, caption=media.caption)
    except Exception as e:
        print(f"Error In Movie Update - {e}")
        pass

async def send_movie_update(bot, file_name, caption):
    try:
        # 1. Clean for Search
        search_name = re.sub(r'https?://\S+', '', file_name)
        search_name = re.sub(r'@\w+', '', search_name).replace('_', ' ').replace('.', ' ')
        
        year_match = re.search(r"\b(19|20)\d{2}\b", caption) or re.search(r"\b(19|20)\d{2}\b", file_name)
        year = year_match.group(0) if year_match else None
        
        if year:
             search_query = search_name[:search_name.find(year) + 4]
        else:
             search_query = search_name

        # 2. Fetch TMDB
        tmdb_data = await fetch_tmdb_data(search_query, year)
        
        title = tmdb_data.get("title", search_name)
        overview = tmdb_data.get("overview", "")
        rating = tmdb_data.get("vote_average", "N/A")
        genres = tmdb_data.get("genres", "Movie")
        poster = tmdb_data.get("poster")
        tmdb_year = tmdb_data.get("release_date", year or "N/A")[:4]

        # 3. Details
        language = await get_formatted_language(caption)
        quality = await get_qualities(caption) or "HDRip"
        display_name = await clean_display_name(file_name)

        # 4. ID Generation & Storage (FIXED LOGIC)
        # Create a URL-safe slug for the "Get File" link
        search_movie_slug = file_name.replace(" ", "-")
        
        # Generate a short unique ID
        unique_id = generate_unique_id(search_movie_slug)
        
        # Save the long slug in memory so we don't need to put it in the button
        movie_slugs[unique_id] = search_movie_slug
        
        if unique_id not in reaction_counts:
            reaction_counts[unique_id] = {"❤️": 0, "👍": 0, "👎": 0, "🔥": 0}
            user_reactions[unique_id] = {}

        # 5. Construct Caption
        full_caption = "#𝑵𝒆𝒘_𝑪𝒐𝒏𝒕𝒆𝒏𝒕_𝑨𝒅𝒅𝒆𝒅 💌\n━━━━━━━━━━━━━━━━━\n"
        full_caption += f"📂 <b>File:</b> {display_name}\n━━━━━━━━━━━━━━━━━\n"
        
        if overview and len(overview) > 10:
            short_overview = overview[:300] + "..." if len(overview) > 300 else overview
            full_caption += f"📝 <b>Storyline:</b>\n{short_overview}\n━━━━━━━━━━━━━━━━━\n"

        full_caption += (
            "╭───────────────╮\n"
            f"│ 🎭 <b>Genre:</b> {genres}\n"
            f"│ 📅 <b>Year:</b> {tmdb_year}\n"
            f"│ 🔊 <b>Language:</b> {language}\n"
            f"│ 💿 <b>Quality:</b> {quality}\n"
            f"│ 🌟 <b>Rating:</b> {rating}/10\n"
            "╰───────────────╯\n\n"
        )

        full_caption += "𝐓𝐨 𝐚𝐜𝐜𝐞𝐬𝐬 𝐭𝐡𝐢𝐬 𝐜𝐨𝐧𝐭𝐞𝐧𝐭, 𝐩𝐥𝐞𝐚𝐬𝐞 𝐜𝐥𝐢𝐜𝐤 𝐭𝐡𝐞 𝐆𝐞𝐭 𝐅𝐢𝐥𝐞 💌 𝐛𝐮𝐭𝐭𝐨𝐧 𝐛𝐞𝐥𝐨𝐰\n━━━━━━━━━━━━━━━━━"

        # 6. Buttons (OPTIMIZED FOR SIZE)
        # Format: r_{unique_id}_{short_code} (Total size approx 10-15 bytes, well under 64 limit)
        buttons = [[
            InlineKeyboardButton(f"❤️ {reaction_counts[unique_id]['❤️']}", callback_data=f"r_{unique_id}_h"),
            InlineKeyboardButton(f"👍 {reaction_counts[unique_id]['👍']}", callback_data=f"r_{unique_id}_l"),
            InlineKeyboardButton(f"👎 {reaction_counts[unique_id]['👎']}", callback_data=f"r_{unique_id}_d"),
            InlineKeyboardButton(f"🔥 {reaction_counts[unique_id]['🔥']}", callback_data=f"r_{unique_id}_f")
        ], [
            # Here we use the full slug because URL buttons don't have the 64 byte limit like callback buttons
            InlineKeyboardButton('💌 Get File 🍿', url=f'https://telegram.me/{temp.U_NAME}?start=getfile-{search_movie_slug}')
        ]]

        if poster:
            await bot.send_photo(chat_id=MOVIE_UPDATE_CHANNEL, photo=poster, caption=full_caption, reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await bot.send_message(chat_id=MOVIE_UPDATE_CHANNEL, text=full_caption, reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)

    except Exception as e:
        print(f"Error in send_movie_update: {e}")

@Client.on_callback_query(filters.regex(r"^r_"))
async def reaction_handler(client, query):
    try:
        # Data Format: r_{unique_id}_{short_code}
        data = query.data.split("_")
        
        if len(data) != 3: 
            return        
        
        unique_id = data[1]
        short_code = data[2]
        user_id = query.from_user.id
        
        # Short code map to Emoji
        code_map = {"h": "❤️", "l": "👍", "d": "👎", "f": "🔥"}
        emoji_to_code = {"❤️": "h", "👍": "l", "👎": "d", "🔥": "f"}
        
        if short_code not in code_map: 
            return
            
        new_emoji = code_map[short_code]
        
        # Retrieve the full movie slug from memory using unique_id
        search_movie_slug = movie_slugs.get(unique_id)
        
        # If slug is missing (bot restarted), try to fallback or just fail gracefully
        if not search_movie_slug:
            await query.answer("Old message data lost due to restart.", show_alert=True)
            return

        if unique_id not in reaction_counts:
            reaction_counts[unique_id] = {"❤️": 0, "👍": 0, "👎": 0, "🔥": 0}
            user_reactions[unique_id] = {}

        if user_id in user_reactions[unique_id]:
            old_emoji = user_reactions[unique_id][user_id]
            if old_emoji == new_emoji:
                await query.answer("You already reacted!", show_alert=False)
                return 
            else:
                reaction_counts[unique_id][old_emoji] -= 1
        
        user_reactions[unique_id][user_id] = new_emoji
        reaction_counts[unique_id][new_emoji] += 1
        
        # Rebuild Buttons with short codes
        updated_buttons = [[
            InlineKeyboardButton(f"❤️ {reaction_counts[unique_id]['❤️']}", callback_data=f"r_{unique_id}_h"),
            InlineKeyboardButton(f"👍 {reaction_counts[unique_id]['👍']}", callback_data=f"r_{unique_id}_l"),
            InlineKeyboardButton(f"👎 {reaction_counts[unique_id]['👎']}", callback_data=f"r_{unique_id}_d"),
            InlineKeyboardButton(f"🔥 {reaction_counts[unique_id]['🔥']}", callback_data=f"r_{unique_id}_f")
        ],[
            InlineKeyboardButton('💌 Get File 🍿', url=f'https://telegram.me/{temp.U_NAME}?start=getfile-{search_movie_slug}')
        ]]
        
        await query.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(updated_buttons))
        
    except Exception as e:
        print("Reaction error:", e)

# --- Helper Functions ---

async def clean_display_name(filename):
    name = re.sub(r'\.\w+$', '', filename)
    name = re.sub(r'https?://\S+|@\w+', '', name)
    unwanted = r'\b(?:1080p|720p|480p|2160p|4k|5k|HEVC|WEB-DL|BluRay|HDRip|HDTC|HDTS|CAMRip|HDCAM|DVDRip|DVDScr|WEBRip|x264|x265|10bit|60fps|AAC|5\.1|Dual|Audio|Multi|Sub|ESub|Line|GB|MB|KB)\b'
    name = re.sub(unwanted, '', name, flags=re.IGNORECASE)
    name = re.sub(r'\b\d+(\.\d+)?\b(?=\s*$)', '', name)
    name = re.sub(r'[\[\(\{\]\)\}]', '', name)
    name = re.sub(r'[._-]', ' ', name)
    return re.sub(r'\s{2,}', ' ', name).strip()

async def get_formatted_language(text):
    found_langs = set()
    text_lower = text.lower()
    for code, full_name in LANG_MAP.items():
        if re.search(r'\b' + re.escape(code) + r'\b', text_lower):
            found_langs.add(full_name)
    if not found_langs: return "Unknown"
    return ", ".join(sorted(found_langs))

async def get_qualities(text):
    quality_list = ["ORG", "HDCAM", "CAMRip", "WEB-DL", "HDRip", "HDTC", "HDTS", "HQ", "DVDscr", "DVDRip", "BluRay", "4K", "1080p"]
    text_lower = text.lower()
    for quality in quality_list:
        if quality.lower() in text_lower:
            return quality
    return None

async def fetch_tmdb_data(query, year=None):
    try:
        params = {"api_key": TMDB_API, "query": query}
        if year: params["year"] = year
        res = requests.get("https://api.themoviedb.org/3/search/movie", params=params, timeout=5)
        results = res.json().get("results", [])
        if not results: return {}
        movie = results[0]
        movie_id = movie.get("id")
        details_res = requests.get(f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API}", timeout=5)
        details = details_res.json()
        poster_path = details.get("poster_path") or movie.get("poster_path")
        backdrop_path = details.get("backdrop_path")
        image_url = None
        if poster_path: image_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
        elif backdrop_path: image_url = f"https://image.tmdb.org/t/p/w500{backdrop_path}"
        genres_list = [g["name"] for g in details.get("genres", [])]
        genres_str = ", ".join(genres_list[:2])
        return {
            "title": details.get("title"),
            "overview": details.get("overview"),
            "vote_average": round(details.get("vote_average", 0), 1),
            "genres": genres_str,
            "release_date": details.get("release_date"),
            "poster": image_url
        }
    except Exception:
        return {}

def generate_unique_id(movie_name):
    return hashlib.md5(movie_name.encode('utf-8')).hexdigest()[:5]
