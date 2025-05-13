import requests
from bs4 import BeautifulSoup
import csv
import os
from openai import OpenAI

# OpenAI키설정
client = OpenAI(api_key="")

# 카테고리
categories = {
    "정치": "100",
    "경제": "101",
    "사회": "102",
    "생활/문화": "103",
    "세계": "104",
    "IT/과학": "105"
}

base_url = "https://news.naver.com/section/"
headers = {"User-Agent": "Mozilla/5.0"} #오류 방지용이랍니다. 서버에서 시행하는 검사 회피용용
csv_file = "네이버뉴스데이터.csv"

#링크 중복 검사
existing_links = set()
if os.path.exists(csv_file):
    with open(csv_file, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            existing_links.add(row["URL"]) #URL로 중복검사를 시행하기

# 크롤링 범위 묻기
print("카테고리:")
for name in categories:
    print(f"- {name}")

choice = input("카테고리와 기사 수를 입력하세요 (예: 정치,10): ")
try:
    selected_category, count_str = [x.strip() for x in choice.split(",")]
    sid = categories.get(selected_category)
    count = int(count_str)
except:
    print("잘못 입력하셨습니다다.")
    exit()

if not sid:
    print("카테고리를 다시 확인하세요.")#위와는 다르게 형식(~~,~)은 맞지만 카테고리명이 없는 경우
    exit()

# 링크 수집
url = base_url + sid#카테고리별로 sid가 달라용
res = requests.get(url, headers=headers)
soup = BeautifulSoup(res.text, "html.parser")

articles = soup.select("div.sa_text")
print(f"[{selected_category}] 총 기사 수: {len(articles)}")

# 기사 처리
new_articles = []
for i in articles:
    if len(new_articles) >= count:
        break

    title_tag = i.select_one("a.sa_text_title")
    if not title_tag:
        continue

    title = title_tag.get_text(strip=True)
    link = title_tag["href"]
    if link in existing_links:
        print(f"중복: {title}")
        continue

    try:
        article_res = requests.get(link, headers=headers)
        article_soup = BeautifulSoup(article_res.text, "html.parser")

        #작성시간
        time_tag = article_soup.select_one("span.media_end_head_info_datestamp_time")
        publish_time = time_tag["data-date-time"] if time_tag and time_tag.has_attr("data-date-time") else "Unknown"

        #기자
        journalist_tag = article_soup.select_one("em.media_end_head_journalist_name")
        journalist = journalist_tag.get_text(strip=True) if journalist_tag else "Unknown"

        #언론사 이미지를 GPT한테 물어서 언론사 확인하기
        press_tag = article_soup.select_one("span.media_end_head_top_logo_text")
        press = press_tag.get_text(strip=True) if press_tag else "Unknown"

        #본문
        content_area = article_soup.select_one("div#newsct_article")
        if not content_area:
            print(f"본문 없음")
            continue

        paragraphs = content_area.find_all("p")
        content_text = " ".join(p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True))
        if not content_text:
            content_text = content_area.get_text(strip=True)

        #GPT로 요약하깅
        prompt = f"다음 뉴스 기사를 한국어로 핵심만 간단히 요약해:\n\n{content_text}"
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "뉴스 요약 시스템이다. 사용자가 입력한 기사를 핵심내용으로 요약해."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
        )

        summary = response.choices[0].message.content.strip()

 # 자극성,연관성 평가
        prompt_eval = f"뉴스 제목: {title}\n\n뉴스 본문: {content_text}\n\n1. 이 제목의 자극성을 10점 만점으로 평가해 숫자로만 표현해줘. (점수가 높을수록 자극적.)\n2. 이 제목이 뉴스 본문과 얼마나 연관 있는지 100점 만점으로 평가해 마찬가지로 숫자로만표현해."
        response_eval = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "넌 뉴스 제목을 분석,평가하는 시스템이다."},
                {"role": "user", "content": prompt_eval}
            ],
            temperature=0.3,
        )
        eval_text = response_eval.choices[0].message.content.strip()

        headline_score = ""
        relevance_score = ""
        for line in eval_text.split("\n"):
            if "자극성" in line:
                headline_score = line.split(":")[-1].strip()
            elif "연관" in line:
                relevance_score = line.split(":")[-1].strip()

        new_articles.append([
            press,
            selected_category,
            title,
            link,
            publish_time,
            journalist,
            summary,
            headline_score,
            relevance_score
        ])

        print(f"수집 및 요약 완료: {title}")

    except Exception as e:
        print(f"에러 발생: {e}")
        continue

# 저장하기기
write_header = not os.path.exists(csv_file)

with open(csv_file, "a", encoding="utf-8-sig", newline="") as f:
    writer = csv.writer(f)
    if write_header:
        writer.writerow(["언론사", "카테고리", "제목", "URL", "발행시간", "기자", "요약", "자극성(10점)", "연관성(100점)"])
    writer.writerows(new_articles)

print(f"\n총 {len(new_articles)}개 기사 저장 완료 (파일: {csv_file})")
