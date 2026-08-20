"""
쿠팡 로켓직구 할인 모니터링 봇
================================
할인율 30% 이상 상품만 디스코드 웹훅으로 알려줍니다.

사용 전 준비
------------
1. .env 파일에 DISCORD_WEBHOOK_URL 입력
2. pip install -r requirements.txt
3. playwright install

★ 처음 실행할 때는 반드시 DEBUG_MODE = True 로 먼저 돌려서
   셀렉터가 실제로 상품을 잘 찾는지 확인하세요.
   (쿠팡은 페이지 구조가 자주 바뀌기 때문에 셀렉터 확인이 필수입니다)
"""

import asyncio
import os
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()

# ====================== 설정 ======================
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
TARGET_URL = "https://shop.coupang.com/rocketjikgujapan/94721?category=189408&platform=p&brandId=0"
DISCOUNT_THRESHOLD = 30  # 이 % 이상만 알림

# True로 두면: 브라우저 창을 띄우고, 스크린샷 + HTML 구조를 저장해서
#              셀렉터가 상품을 잘 찾는지 눈으로 확인할 수 있습니다.
DEBUG_MODE = True
# ==================================================


async def scrape_products():
    """페이지에서 상품 정보를 가져오는 함수.
    ★ 셀렉터(query_selector_all 안의 문자열)는 실제 페이지 구조에 맞게
      개발자도구(F12 → Elements 탭)로 확인 후 반드시 수정하세요."""
    products = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not DEBUG_MODE,  # 디버그 모드에서는 창을 띄워서 눈으로 확인
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="ko-KR",
        )
        page = await context.new_page()

        try:
            await page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(3000)

            if DEBUG_MODE:
                # 디버깅용: 현재 페이지 스크린샷 + HTML을 저장해서
                # 실제 셀렉터가 무엇인지 확인할 수 있게 함
                await page.screenshot(path="debug_screenshot.png", full_page=True)
                html = await page.content()
                with open("debug_page.html", "w", encoding="utf-8") as f:
                    f.write(html)
                print("디버그용 debug_screenshot.png / debug_page.html 저장 완료")
                print("이 파일을 열어 상품 카드의 실제 class 이름을 확인한 뒤")
                print("아래 query_selector_all 안의 셀렉터를 수정하세요.")

            # ★★★ 아래 셀렉터들을 실제 페이지에 맞게 수정하세요 ★★★
            items = await page.query_selector_all(
                "li.search-product, div.product-item, article"
            )

            for item in items:
                try:
                    name_el = await item.query_selector(
                        "div.name, a > span, .product-title"
                    )
                    name = await name_el.inner_text() if name_el else None

                    link_el = await item.query_selector("a")
                    href = await link_el.get_attribute("href") if link_el else ""
                    if href and not href.startswith("http"):
                        href = "https://www.coupang.com" + href

                    discount_el = await item.query_selector(
                        ".discount-rate, .badge, span:has-text('%')"
                    )
                    discount_text = await discount_el.inner_text() if discount_el else "0"
                    discount = int("".join(filter(str.isdigit, discount_text)) or 0)

                    price_el = await item.query_selector(
                        ".price-value, .sale-price, strong"
                    )
                    price = await price_el.inner_text() if price_el else "-"

                    original_el = await item.query_selector(
                        ".base-price, .original-price, del"
                    )
                    original = await original_el.inner_text() if original_el else "-"

                    img_el = await item.query_selector("img")
                    img = await img_el.get_attribute("src") if img_el else ""

                    if name and discount >= DISCOUNT_THRESHOLD:
                        products.append(
                            {
                                "name": name.strip(),
                                "url": href,
                                "discount": discount,
                                "price": price.strip(),
                                "original": original.strip(),
                                "image": img,
                            }
                        )
                except Exception as e:
                    print(f"상품 파싱 오류: {e}")
                    continue

        except Exception as e:
            print(f"페이지 접근 실패: {e}")
        finally:
            await browser.close()

    return products


def send_discord(products: list):
    """할인 상품들을 디스코드 웹훅으로 전송 (임베드 최대 10개/메시지 제한 대응)"""
    if not DISCORD_WEBHOOK_URL:
        print("DISCORD_WEBHOOK_URL이 설정되지 않았습니다. .env 파일을 확인하세요.")
        return

    if not products:
        print(f"[{datetime.now()}] {DISCOUNT_THRESHOLD}% 이상 할인 상품 없음")
        return

    for i in range(0, len(products), 8):
        batch = products[i : i + 8]
        embeds = []

        for item in batch:
            embed = {
                "title": f"🔥 {item['discount']}% 할인 · {item['name'][:80]}",
                "url": item["url"],
                "color": 15158332,
                "fields": [
                    {"name": "할인율", "value": f"**{item['discount']}%**", "inline": True},
                    {"name": "할인가", "value": item["price"], "inline": True},
                    {"name": "정가", "value": f"~~{item['original']}~~", "inline": True},
                ],
                "footer": {"text": "로켓직구 일본스토어 • 30%↑ 필터"},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if item.get("image"):
                embed["thumbnail"] = {"url": item["image"]}
            embeds.append(embed)

        payload = {"username": "쿠팡 로켓직구 세일봇", "embeds": embeds}

        resp = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if resp.status_code in (200, 204):
            print(f"[{datetime.now()}] {len(batch)}개 상품 전송 완료")
        else:
            print(f"[{datetime.now()}] 전송 실패: {resp.status_code} - {resp.text}")


async def main():
    print(f"[{datetime.now()}] 모니터링 시작...")
    products = await scrape_products()
    print(f"할인율 {DISCOUNT_THRESHOLD}% 이상 상품 {len(products)}개 발견")
    send_discord(products)


if __name__ == "__main__":
    asyncio.run(main())
