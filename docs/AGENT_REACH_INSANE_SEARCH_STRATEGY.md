# Agent Reach & Insane Search Strategy

## 결론

Zespa Review Intelligence 프로젝트에서 `agent-reach`와 `insane-search`는 쇼핑몰 크롤러를 대체하기보다, 커뮤니티/SNS/웹 전반의 공개 언급을 넓히는 수집 계층으로 활용한다.

- `agent-reach`: 실제 CLI/채널 기반 수집 계층
- `insane-search`: 차단/JS/캡차/동적 사이트 대응을 위한 progressive fallback 전략

## 현재 환경 상태

`agent-reach doctor` 기준 현재 사용 가능:

- GitHub repo/code search
- YouTube video/subtitle extraction
- Reddit posts/comments via `rdt-cli`
- V2EX public API
- RSS/Atom feeds
- Jina Reader web reading (`https://r.jina.ai/URL`)
- Bilibili search/video via `yt-dlp`/API

추가 설정하면 확장 가능:

- Twitter/X
- Xiaohongshu
- Weibo
- Douyin
- LinkedIn
- Exa semantic web search via mcporter

`insane-search`는 현재 Hermes skill로 존재하지만 별도 CLI command는 확인되지 않았다. 따라서 프로젝트에서는 독립 실행 도구로 가정하지 않고, `curl_cffi`, Jina Reader, RSS, Playwright, site-search fallback 같은 접근 전략으로 반영한다.

## 이 프로젝트에서의 역할 분담

### 1. Agent Reach 활용 영역

#### Reddit

한국 브랜드 직접 언급은 적을 수 있지만, `massage chair`, `foot massager`, `leg massager`, `Bodyfriend` 같은 영어권 비교 맥락을 볼 수 있다.

수집 후보:

- `rdt` 기반 subreddit/search
- 키워드: `Bodyfriend`, `Zespa`, `leg massager`, `foot massager`, `massage chair`, `Korean massage chair`

#### YouTube

안마기/안마의자 리뷰 영상, 쇼츠, 제품 비교 콘텐츠 확인에 유용하다.

수집 후보:

- `yt-dlp --default-search ytsearch:`
- 제목, 채널명, 조회수, 업로드일, URL, 자막 가능 시 요약

검색어:

- 제스파 후기
- 제스파 발마사지기
- 제스파 종아리 마사지기
- 바디프렌드 팔콘 후기
- 안마의자 추천
- 부모님 선물 마사지기

#### RSS/Atom

블로그/뉴스/가격비교 사이트 중 RSS가 있는 경우 안정적인 수집원이 된다.

#### V2EX/Bilibili

한국 브랜드 직접성은 낮지만, 중국/글로벌 마사지기 트렌드 보조 지표로 활용 가능.

#### Jina Reader

JS/차단/복잡한 HTML 사이트를 Markdown 텍스트로 읽는 fallback. 커뮤니티/블로그/검색 결과의 본문 추출 보조로 사용한다.

예:

```bash
curl -s "https://r.jina.ai/https://search.daum.net/search?w=tot&q=제스파+후기"
```

### 2. Insane Search 활용 영역

`insane-search`는 다음 순서의 progressive fallback 정책으로 반영한다.

1. 공식 API/공개 API
2. RSS/Atom
3. 일반 HTTP + BeautifulSoup
4. Jina Reader
5. curl_cffi 기반 TLS fingerprint 완화
6. Playwright 렌더링
7. 실패 시 차단 상태 기록, 무리한 우회 중단

주의:

- Instagram/Threads/네이버 카페처럼 로그인/캡차/약관 리스크가 큰 플랫폼은 무리하게 우회하지 않는다.
- 비공개/회원 전용 콘텐츠는 수집하지 않는다.
- 원문 전체 저장보다 URL/제목/스니펫/분류 태그 중심으로 저장한다.

## 추천 수집 파이프라인

### Phase A: 공개 웹 mention collector

우선 구현 대상:

- Daum search
- Jina Reader wrapped search pages
- RSS/Atom
- Google/Bing/DuckDuckGo 대체 가능 시
- site-search queries

출력:

- `data/social_mentions.csv`
- `data/social_latest.json`
- `reports/social-latest-report.md`

### Phase B: Agent Reach channels

추가 대상:

- Reddit via `rdt`
- YouTube via `yt-dlp`
- RSS feeds
- V2EX/Bilibili 보조

### Phase C: Optional login/API channels

후순위:

- X/Twitter CLI auth
- Instagram/Threads 공식/검색 기반 접근
- 네이버 카페 공개 검색
- Exa semantic search via mcporter

## 데이터 스키마

`data/social_mentions.csv`:

- collected_at_kst
- platform
- source_name
- source_method
- brand
- query
- title
- snippet
- url
- author
- published_at
- engagement_score
- sentiment
- mention_type
- product_cluster
- raw_status

## 대시보드 반영

기존 dashboard에 다음 섹션 추가:

1. Social & Community Voice
2. Platform Coverage
3. Mention Type Breakdown
4. Sentiment Split
5. Fresh Signals
6. Opportunity Map

## 운영 원칙

- 매일 1회 저빈도 실행
- 실패/차단도 데이터로 기록
- 대량 원문 수집 금지
- 로그인/회원 전용/비공개 글 수집 금지
- 우회보다 안정적인 공개 데이터 계층화 우선
