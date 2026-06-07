# Zespa Social & Community Intelligence Plan

## 목적

쇼핑몰 상품 카드/후기 중심 조사를 넘어, 한국 커뮤니티·SNS·카페·블로그·Instagram·Threads 등에서 제스파(Zespa)와 바디프렌드(Bodyfriend)가 실제로 어떻게 언급되는지 추적한다.

핵심 질문:

- 사람들은 제스파를 어떤 상황에서 언급하는가?
- 제스파는 '가성비 마사지기', '부모님 선물', '소형 마사지기', '온열/종아리/발 마사지기' 중 어디에 강한가?
- 바디프렌드와 비교될 때 가격/AS/프리미엄/안마의자 이미지가 어떻게 갈리는가?
- 반복되는 불만/칭찬 키워드는 무엇인가?
- 특정 커뮤니티나 SNS에서 구매 전환 가능성이 높은 주제가 있는가?

## 소스 우선순위

### 1. 공개 웹/검색 기반: 우선 구현

- 네이버 블로그 검색 결과
- 다음/카카오 검색 결과
- 구글/Bing/DuckDuckGo 검색 결과
- 티스토리/브런치/개인 블로그
- 공개 뉴스/리뷰 기사
- 다나와/에누리/가격비교의 공개 텍스트

장점:
- 로그인 불필요
- 매일 자동화 안정성 높음
- 법적/정책 리스크 낮음

단점:
- 실시간 SNS 반응은 제한적
- 네이버 계열은 bot/captcha 대응 필요

### 2. 한국 커뮤니티: 선별 구현

후보:

- 디시인사이드
- 더쿠
- 뽐뿌
- 클리앙
- 루리웹
- 맘카페/육아/부모님 선물 관련 공개 게시판
- 네이트판/오늘의집 커뮤니티/인테리어·생활 커뮤니티

수집 방식:

- 자체 검색 페이지가 공개 접근 가능하면 HTML 수집
- 막히면 검색엔진의 `site:` 검색 결과를 통해 간접 수집
- 원문 전문 대량 저장보다 URL/제목/스니펫/날짜/출처/감성 태그 중심 저장

중요 키워드:

- 제스파 후기
- 제스파 발마사지기
- 제스파 종아리 마사지기
- 제스파 안마기 추천
- 제스파 고장
- 제스파 AS
- 부모님 마사지기 추천
- 바디프렌드 팔콘 후기
- 바디프랜드 AS
- 안마의자 추천

### 3. Instagram / Threads: 제한적·보수적 접근

현실:

- Instagram/Threads는 공식 API 접근 제한이 강하고 로그인/세션/봇 탐지가 강함.
- 무리한 scraping은 계정/세션 리스크가 있음.
- 자동화는 공개 검색/해시태그 검색 결과의 제한적 메타데이터 수준부터 시작하는 것이 안전함.

가능한 접근:

- 공개 웹 검색: `site:instagram.com 제스파`, `site:threads.net 제스파`
- Jina Reader/검색엔진 결과를 통한 URL·스니펫 수집
- 수동 계정 로그인 기반 자동화는 별도 승인 후, 저빈도·읽기 전용으로만 운영
- 공식 Meta Graph API는 비즈니스 계정/권한 요건 확인 필요

수집 후보 필드:

- platform: instagram / threads
- author/display name 가능 시
- post URL
- title/snippet/caption 일부
- hashtags
- like/comment count 가능 시
- collected_at_kst
- brand/query
- sentiment/intent tag

### 4. 네이버 카페: 중요하지만 난이도 높음

현실:

- 네이버 카페는 로그인/멤버십/검색 제한이 많음.
- 비공개/회원 전용 글은 수집하지 않는다.
- 공개 검색 결과에 노출되는 제목/스니펫/URL 중심으로 시작.

가능한 접근:

- 네이버/구글 검색의 `site:cafe.naver.com 제스파 후기`
- 공개 글만 수집
- 카페명/게시일/스니펫/URL 저장
- 로그인 세션 기반 크롤링은 정책/계정 리스크가 있어 후순위

## 분석 분류 체계

### Mention Type

- 구매 후기
- 구매 전 질문
- 추천 요청
- 비교 질문
- AS/고장 불만
- 선물/부모님 관련
- 바이럴/광고 의심
- 중고/리퍼/렌탈
- 기타

### Sentiment

- positive
- neutral
- negative
- mixed
- unknown

### Product/Use Case Cluster

- 발마사지기
- 종아리 마사지기
- 목/어깨 마사지기
- 안마의자
- 마사지건
- 온열/공기압
- 부모님 선물
- AS/고장/내구성
- 가격/가성비

## 데이터 파일 제안

- `data/social_mentions.csv`
  - collected_at_kst
  - platform
  - source_name
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

- `data/social_latest.json`
  - 브랜드별 언급량
  - 플랫폼별 언급량
  - 긍정/부정 비율
  - 상위 키워드
  - 최근 중요 게시물
  - 신규 급증 이슈

- `reports/social-latest-report.md`
  - 매일 커뮤니티/SNS 요약

## 대시보드 확장

기존 상품/가격 대시보드에 다음 섹션 추가:

1. Social Voice Overview
   - Zespa vs Bodyfriend 언급량
   - 긍정/부정/중립 비율
   - 주요 플랫폼 분포

2. Why People Mention It
   - 부모님 선물
   - 가성비
   - AS/고장
   - 마사지 부위
   - 프리미엄/렌탈

3. Fresh Signals
   - 최근 24~72시간 신규 언급
   - 급증 키워드
   - 부정 이슈 알림

4. Opportunity Map
   - Zespa가 강한 영역
   - Bodyfriend가 강한 영역
   - Zespa가 콘텐츠/광고로 파고들 수 있는 틈

## MVP 순서

1. 검색엔진 기반 공개 mention collector 추가
2. 다음 검색/블로그/커뮤니티 site 검색부터 수집
3. `social_mentions.csv`와 `social_latest.json` 생성
4. 기존 대시보드에 Social 섹션 추가
5. 매일 cron에서 상품 수집 + social 수집을 함께 실행
6. Instagram/Threads/네이버 카페는 공개 검색 결과 기반으로 먼저 넣고, 로그인/공식 API는 후속 검토

## 운영 원칙

- 비공개/로그인 전용/회원 전용 콘텐츠는 수집하지 않는다.
- 원문 전체를 대량 저장하기보다 제목/스니펫/URL/분석 태그 중심으로 저장한다.
- 플랫폼이 차단/캡차를 반환하면 우회하지 말고 `source_status`에 기록한다.
- 매일 1회 저빈도 수집으로 시작한다.
