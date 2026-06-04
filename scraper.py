"""
Social media trend scraper.
Fetches top posts from X (Twitter) API v2 and YouTube Data API v3,
then analyzes marketing trends with Claude.

Usage:
    python scraper.py <keyword>

Required env vars:
    X_BEARER_TOKEN       - X (Twitter) API v2 bearer token
    YOUTUBE_API_KEY      - YouTube Data API v3 key
    ANTHROPIC_API_KEY    - Anthropic API key
"""

import json
import os
import sys
from datetime import datetime, timezone

import anthropic
import requests


def fetch_x_posts(keyword: str, max_results: int = 20) -> list[dict]:
    bearer_token = os.environ["X_BEARER_TOKEN"]
    url = "https://api.twitter.com/2/tweets/search/recent"
    params = {
        "query": f"{keyword} -is:retweet lang:en",
        "max_results": max_results,
        "tweet.fields": "created_at,public_metrics,author_id",
        "expansions": "author_id",
        "user.fields": "username",
    }
    headers = {"Authorization": f"Bearer {bearer_token}"}
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    users = {u["id"]: u["username"] for u in data.get("includes", {}).get("users", [])}
    posts = []
    for tweet in data.get("data", []):
        metrics = tweet.get("public_metrics", {})
        engagement = (
            metrics.get("like_count", 0)
            + metrics.get("retweet_count", 0)
            + metrics.get("reply_count", 0)
            + metrics.get("quote_count", 0)
        )
        username = users.get(tweet.get("author_id", ""), "unknown")
        posts.append(
            {
                "source": "x",
                "title": tweet["text"][:280],
                "engagement": engagement,
                "url": f"https://twitter.com/{username}/status/{tweet['id']}",
                "date": tweet.get("created_at", ""),
            }
        )
    return posts


def fetch_youtube_videos(keyword: str, max_results: int = 10) -> list[dict]:
    api_key = os.environ["YOUTUBE_API_KEY"]
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "order": "relevance",
        "maxResults": max_results,
        "key": api_key,
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    search_data = resp.json()

    video_ids = [item["id"]["videoId"] for item in search_data.get("items", [])]
    if not video_ids:
        return []

    stats_url = "https://www.googleapis.com/youtube/v3/videos"
    stats_params = {
        "part": "statistics",
        "id": ",".join(video_ids),
        "key": api_key,
    }
    stats_resp = requests.get(stats_url, params=stats_params, timeout=15)
    stats_resp.raise_for_status()
    stats_by_id = {
        v["id"]: v.get("statistics", {}) for v in stats_resp.json().get("items", [])
    }

    videos = []
    for item in search_data.get("items", []):
        vid_id = item["id"]["videoId"]
        snippet = item["snippet"]
        stats = stats_by_id.get(vid_id, {})
        engagement = int(stats.get("viewCount", 0)) + int(
            stats.get("likeCount", 0)
        ) * 10
        videos.append(
            {
                "source": "youtube",
                "title": snippet.get("title", ""),
                "engagement": engagement,
                "url": f"https://www.youtube.com/watch?v={vid_id}",
                "date": snippet.get("publishedAt", ""),
            }
        )
    return videos


def analyze_trends(keyword: str, posts: list[dict]) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    summary = json.dumps(posts, indent=2)
    prompt = f"""You are a marketing analyst. Below is social media data collected for the keyword "{keyword}".
Analyze the content and engagement metrics to identify:
1. Key themes and messaging patterns
2. Audience sentiment
3. Top-performing content types
4. Actionable marketing recommendations

Data:
{summary}
"""
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def scrape(keyword: str) -> dict:
    print(f"Fetching X posts for '{keyword}'...")
    x_posts = fetch_x_posts(keyword)

    print(f"Fetching YouTube videos for '{keyword}'...")
    yt_videos = fetch_youtube_videos(keyword)

    all_posts = x_posts + yt_videos
    all_posts.sort(key=lambda p: p["engagement"], reverse=True)

    print("Analyzing trends with Claude...")
    analysis = analyze_trends(keyword, all_posts)

    result = {
        "keyword": keyword,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "total_posts": len(all_posts),
        "posts": all_posts,
        "trend_analysis": analysis,
    }
    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python scraper.py <keyword>")
        sys.exit(1)

    keyword = " ".join(sys.argv[1:])
    result = scrape(keyword)

    output_path = f"trends_{keyword.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)

    print(f"\nResults saved to {output_path}")
    print(f"\n--- Trend Analysis ---\n{result['trend_analysis']}")


if __name__ == "__main__":
    main()
