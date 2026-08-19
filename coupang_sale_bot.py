import asyncio
import requests
from datetime import datetime, timezone
from playwright.async_api import async_playwright
import os
from dotenv import load_dotenv

load_dotenv()

# ====================== 설정 ======================
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")  # .env에 넣어두세요
TARGET_URL = "https://shop.coupang.com/rocketjikgujapan/94721?category=189408&platform=p&brandId=0"
DISCOUNT_THRESHOLD = 30  # 30% 이상만
# ==================================================

async def scrape_products():
    """페이지에서 상품 정보를 가져오는 함수 (셀렉터는 직접 수정 필요)"""
    products = []

    async with async_playwright() as p:
        # 헤드리스를 False로 하면 차단을 조금 덜 받을 수 있음
        browser = await p.chromium.launch(
            headless=False,  # 테스트 후 True로 변경 가능
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="ko-KR"
        )
        page = await context.new_page()

        try:
            await page.goto(TARGET_URL, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(3000)  # 페이지 로딩 대기

            # ★★★ 여기 셀렉터를 실제 페이지에 맞게 수정해야 합니다 ★★★
            # 개발자도구(F12)로 상품 카드, 할인율, 가격, 링크, 이미지를 확인하세요
            items = await page.query_selector_all("li.search-product, div.product-item, article")  # 예시

            for item in items:
                try:
                    # 상품명
                    name_el = await item.query_selector("div.name, a > span, .product-title")
                    name = await name_el.inner_text() if name_el else "이름 없음"

                    # 상품 링크
                    link_el = await item.query_selector("a")
                    href = await link_el.get_attribute("href") if link_el else ""
                    if href and not href.startswith("http"):
                        href = "https://www.coupang.com" + href

                    # 할인율 (예: "45%" 또는 "45")
                    discount_el = await item.query_selector(".discount-rate, .badge, span:has-text('%')")
                    discount_text = await discount_el.inner_text() if discount_el else "0"
                    discount = int("".join(filter(str.isdigit, discount_text)) or 0)

                    # 할인가
                    price_el = await item.query_selector(".price-value, .sale-price, strong")
                    price = await price_el.inner_text() if price_el else "-"

                    # 정가
                    original_el = await item.query_selector(".base-price, .original-price, del")
                    original = await original_el.inner_text() if original_el else "-"

                    # 썸네일
                    img_el = await item.query_selector("img")
                    img = await img_el.get_attribute("src") if img_el else ""

                    if discount >= DISCOUNT_THRESHOLD:
                        products.append({
                            "name": name.strip(),
                            "url": href,
                            "discount": discount,
                            "price": price.strip(),
                            "original": original.strip(),
                            "image": img
                        })
                except Exception as e:
                    print(f"상품 파싱 오류: {e}")
                    continue

        except Exception as e:
            print(f"페이지 접근 실패: {e}")
        finally:
            await browser.close()

    return products


def send_discord(products: list):
    """할인 상품들을 디스코드 웹훅으로 전송"""
    if not products:
        print("30% 이상 할인 상품이 없습니다.")
        return

    # 너무 많으면 나눠서 보내기 (한 메시지에 임베드 10개 제한)
    for i in range(0, len(products), 8):
        batch = products[i:i+8]
        embeds = []

        for p in batch:
            embed = {
                "title": f"🔥 {p['discount']}% 할인 · {p['name'][:80]}",
                "url": p["url"],
                "color": 15158332,  # 주황/빨강
                "fields": [
                    {"name": "할인율", "value": f"**{p['discount']}%**", "inline": True},
                    {"name": "할인가", "value": p["price"], "inline": True},
                    {"name": "정가", "value": f"~~{p['original']}~~", "inline": True},
                ],
                "thumbnail": {"url": p["image"]} if p["image"] else None,
                "footer": {"text": "로켓직구 일본스토어 • 30%↑ 필터"},
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            # thumbnail이 None이면 제거
            if not embed["thumbnail"]:
                del embed["thumbnail"]
            embeds.append(embed)

        payload = {
            "username": "쿠팡 로켓직구 세일봇",
            "embeds": embeds
        }

        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        if response.status_code in (200, 204):
            print(f"{len(batch)}개 상품 전송 완료")
        else:
            print(f"전송 실패: {response.status_code} - {response.text}")


async def main():
    print(f"[{datetime.now()}] 모니터링 시작...")
    products = await scrape_products()
    print(f"할인율 {DISCOUNT_THRESHOLD}% 이상 상품 {len(products)}개 발견")
    send_discord(products)


if __name__ == "__main__":
    asyncio.run(main())
