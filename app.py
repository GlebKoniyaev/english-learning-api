from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
import requests
from bs4 import BeautifulSoup
import re
import threading
import json
import httpx
import asyncio
import httpx

app = FastAPI()

# Монтирование статических файлов
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def read_root():
    """Перенаправление на веб-интерфейс"""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/web")


@app.get("/web")
def web_interface():
    """Веб-интерфейс для удобного использования"""
    from fastapi.responses import HTMLResponse
    with open("static/index.html", "r", encoding="utf-8") as f:
        content = f.read()
    return HTMLResponse(content=content)


# Initialize SQLite database
conn = sqlite3.connect('words.db', check_same_thread=False)
cursor = conn.cursor()
db_lock = threading.Lock()
cursor.execute('''
CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    word TEXT NOT NULL,
    url TEXT NOT NULL,
    translation_google TEXT,
    translation_lingva TEXT,
    translation_mymemory TEXT,
    difficulty_level INTEGER DEFAULT 1,
    next_review_date TEXT DEFAULT CURRENT_DATE,
    review_count INTEGER DEFAULT 0,
    ease_factor REAL DEFAULT 2.5,
    interval_days INTEGER DEFAULT 1
)
''')
# Add new columns if they don't exist
columns_to_add = [
    'difficulty_level INTEGER DEFAULT 1',
    'next_review_date TEXT DEFAULT CURRENT_DATE',
    'review_count INTEGER DEFAULT 0',
    'ease_factor REAL DEFAULT 2.5',
    'interval_days INTEGER DEFAULT 1'
]
for column in columns_to_add:
    try:
        cursor.execute(f'ALTER TABLE words ADD COLUMN {column}')
    except sqlite3.OperationalError:
        pass
# Create unique index on word to prevent duplicates
try:
    cursor.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_word ON words(word)')
except sqlite3.OperationalError:
    pass
conn.commit()


class Item(BaseModel):
    id: int
    name: str
    description: Optional[str] = None


class Word(BaseModel):
    id: int
    name: str
    url: str
    description: Optional[str] = None
    translation_google: Optional[str] = None
    translation_lingva: Optional[str] = None
    translation_mymemory: Optional[str] = None
    difficulty_level: int = 1
    next_review_date: Optional[str] = None
    review_count: int = 0
    ease_factor: float = 2.5
    interval_days: int = 1


class UrlModel(BaseModel):
    url: str


class ReviewModel(BaseModel):
    quality: int

    class Config:
        schema_extra = {
            "example": {
                "quality": 3
            }
        }


# In-memory storage for unused items, can be removed
items: List[Item] = []


@app.get("/items", response_model=List[Item], summary="Get all items (example endpoint)")
def read_items():
    return items


@app.get("/items/{item_id}", response_model=Item, summary="Get an item by ID (example endpoint)")
def read_item(item_id: int):
    item = next((item for item in items if item.id == item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@app.post("/items", response_model=Item, summary="Create an item (example endpoint)")
def create_item(item: Item):
    if any(i.id == item.id for i in items):
        raise HTTPException(
            status_code=400, detail="Item with this ID already exists")
    items.append(item)
    return item


@app.put("/items/{item_id}", response_model=Item, summary="Update an item (example endpoint)")
def update_item(item_id: int, updated_item: Item):
    item = next((item for item in items if item.id == item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    item.name = updated_item.name
    item.description = updated_item.description
    return item


@app.delete("/items/{item_id}", summary="Delete an item (example endpoint)")
def delete_item(item_id: int):
    item = next((item for item in items if item.id == item_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    items.remove(item)
    return {"message": "Item deleted"}


def extract_english_words(text):
    # Extract words that are likely English (alphabetic, length > 2)
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text)
    # Convert to lowercase and remove duplicates
    words_lower = [word.lower() for word in words]
    return list(set(words_lower))  # Remove duplicates


async def translate_google(word: str, client: httpx.AsyncClient) -> Optional[str]:
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ru&dt=t&q={word}"
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
        return data[0][0][0] if data and data[0] else None
    except (httpx.RequestError, IndexError, json.JSONDecodeError) as e:
        print(f"Google Translate error: {e}")
        return None


async def translate_lingva(word: str, client: httpx.AsyncClient) -> Optional[str]:
    try:
        response = await client.get(f'https://lingva.ml/api/v1/en/ru/{word}')
        response.raise_for_status()
        data = response.json()
        return data.get('translation')
    except (httpx.RequestError, json.JSONDecodeError) as e:
        print(f"Lingva Translate error: {e}")
        return None


async def translate_mymemory(word: str, client: httpx.AsyncClient) -> Optional[str]:
    try:
        response = await client.get(f'https://api.mymemory.translated.net/get?q={word}&langpair=en|ru')
        response.raise_for_status()
        data = response.json()
        return data.get('responseData', {}).get('translatedText')
    except (httpx.RequestError, json.JSONDecodeError) as e:
        print(f"MyMemory Translate error: {e}")
        return None


@app.post("/process_url")
async def process_url(request_data: UrlModel):
    url = request_data.url
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        text = soup.get_text()
        words = extract_english_words(text)

        # Save to database (without translations initially)
        with db_lock:
            for word in words:
                cursor.execute(
                    'INSERT OR IGNORE INTO words (word, url, difficulty_level, next_review_date, review_count, ease_factor, interval_days) VALUES (?, ?, 1, date("now"), 0, 2.5, 1)',
                    (word, url))
            conn.commit()

        return {"message": f"Extracted and saved {len(words)} words from {url}"}
    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=f"Error fetching URL: {e}")
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"An unexpected error occurred: {str(e)}")


@app.get("/words", response_model=List[Word])
def get_words():
    with db_lock:
        cursor.execute(
            'SELECT id, word, url, translation_google, translation_lingva, translation_mymemory, difficulty_level, next_review_date, review_count, ease_factor, interval_days FROM words')
        rows = cursor.fetchall()
        return [Word(id=row[0], name=row[1], url=row[2], translation_google=row[3], translation_lingva=row[4], translation_mymemory=row[5], difficulty_level=row[6], next_review_date=row[7], review_count=row[8], ease_factor=row[9], interval_days=row[10]) for row in rows]


@app.get("/next_word")
async def get_next_word():
    """Получить следующее слово для изучения с переводами"""
    with db_lock:
        cursor.execute('''
            SELECT id, word, url, translation_google, translation_lingva, translation_mymemory, difficulty_level, next_review_date, review_count, ease_factor, interval_days 
            FROM words 
            WHERE date(next_review_date) <= date('now')
            ORDER BY difficulty_level ASC, review_count ASC
            LIMIT 1
        ''')
        row = cursor.fetchone()

    if row:
        word_id, word, url, google, lingva, mymemory, difficulty_level, next_review_date, review_count, ease_factor, interval_days = row

        # Если переводы отсутствуют, переводим сейчас
        if not google or not lingva or not mymemory:
            async with httpx.AsyncClient() as client:
                google, lingva, mymemory = await asyncio.gather(
                    translate_google(word, client),
                    translate_lingva(word, client),
                    translate_mymemory(word, client)
                )

            # Сохраняем переводы в базу
            with db_lock:
                cursor.execute(
                    'UPDATE words SET translation_google = ?, translation_lingva = ?, translation_mymemory = ? WHERE id = ?',
                    (google, lingva, mymemory, word_id)
                )
                conn.commit()

        return Word(id=word_id, name=word, url=url, translation_google=google, translation_lingva=lingva, translation_mymemory=mymemory, difficulty_level=difficulty_level, next_review_date=next_review_date, review_count=review_count, ease_factor=ease_factor, interval_days=interval_days)
    else:
        return {"message": "Нет слов для изучения сегодня"}


@app.post("/review_word/{word_id}")
def review_word(word_id: int, review: ReviewModel = None, quality: int = None):
    """
    Отметить качество ответа для слова
    quality: 0-5 (0=полностью забыл, 5=легко вспомнил)
    """
    if review is not None:
        quality_value = review.quality
        print(
            f"DEBUG: Received review from body: quality={quality_value}, type={type(quality_value)}")
    elif quality is not None:
        quality_value = quality
        print(
            f"DEBUG: Received quality from query param: quality={quality_value}, type={type(quality_value)}")
    else:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400, detail="Either provide quality in request body or as query parameter")

    # Validate quality range
    if not isinstance(quality_value, int) or quality_value < 0 or quality_value > 5:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400, detail=f"Quality must be an integer between 0 and 5, got: {quality_value} (type: {type(quality_value)})")

    quality = quality_value
    with db_lock:
        # Получить текущее слово
        cursor.execute(
            'SELECT review_count, ease_factor, interval_days FROM words WHERE id = ?', (word_id,))
        row = cursor.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Word not found")

        review_count, ease_factor, interval_days = row

        # Anki algorithm
        if quality >= 3:
            # Правильный ответ
            if review_count == 0:
                interval_days = 1
            elif review_count == 1:
                interval_days = 6
            else:
                interval_days = int(interval_days * ease_factor)

            # Обновить ease factor
            ease_factor = max(
                1.3, ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
        else:
            # Неправильный ответ
            interval_days = 1
            review_count = max(0, review_count - 1)

        review_count += 1

        # Обновить дату следующего повторения
        cursor.execute('''
            UPDATE words 
            SET next_review_date = date('now', '+' || ? || ' days'),
                review_count = ?,
                ease_factor = ?,
                interval_days = ?
            WHERE id = ?
        ''', (interval_days, review_count, ease_factor, interval_days, word_id))

        conn.commit()

    return {"message": f"Word review updated. Next review in {interval_days} days"}


@app.get("/study_stats")
def get_study_stats():
    """Получить статистику изучения"""
    with db_lock:
        cursor.execute('SELECT COUNT(*) FROM words')
        total_words = cursor.fetchone()[0]

        cursor.execute(
            'SELECT COUNT(*) FROM words WHERE date(next_review_date) <= date("now")')
        due_words = cursor.fetchone()[0]

        cursor.execute('SELECT AVG(review_count) FROM words')
        avg_reviews = cursor.fetchone()[0] or 0

        cursor.execute('SELECT COUNT(*) FROM words WHERE review_count > 0')
        learned_words = cursor.fetchone()[0]

    return {
        "total_words": total_words,
        "due_words": due_words,
        "learned_words": learned_words,
        "average_reviews": round(avg_reviews, 2)
    }


@app.delete("/words")
@app.delete("/words")
def clear_words():
    with db_lock:
        cursor.execute('DELETE FROM words')
        conn.commit()
    return {"message": "All words deleted successfully"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
