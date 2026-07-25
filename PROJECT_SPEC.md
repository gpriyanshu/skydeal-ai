\# SkyDeal AI - Product Requirements



\## Vision



SkyDeal AI is an intelligent flight deal monitoring system that continuously scans flight prices and automatically notifies users whenever an exceptional deal is found.



This is NOT a simple price checker.



The goal is to build a production-ready system that can later support thousands of users.



\---



\# Functional Requirements



\## Flight Scanning



\- Scan flights every hour

\- Configurable interval

\- Support multiple origin airports

\- Default origins:

&#x20;   - DEL

&#x20;   - BOM

&#x20;   - BLR

&#x20;   - HYD

&#x20;   - MAA

&#x20;   - CCU

&#x20;   - COK



The scanner should reuse the existing implementation from:



https://github.com/shadyvb/mcp-skyscanner



If Everywhere search is unavailable, design the system so it can be added later without major refactoring.



\---



\# Deal Detection



Detect deals based on:



\- Current Price

\- Historical Average

\- Historical Lowest Price

\- Percentage Discount

\- Historical Trend



Deal Categories:



\- Normal

\- Good Deal

\- Great Deal

\- Super Deal



Notify only:



\- Great Deal

\- Super Deal



\---



\# Historical Data



Store every scan.



Track:



\- lowest price

\- highest price

\- average price

\- first seen

\- last seen



\---



\# Notifications



Primary:



Telegram



Secondary:



Email



Support multiple users.



Each user has:



\- chat id

\- preferred countries

\- preferred airports

\- budget

\- notification enabled



\---



\# Telegram Commands



/start



/help



/deals



/watch



/history



/settings



/stop



\---



\# Scheduler



Run every hour.



Must be configurable.



\---



\# Database



SQLite



Tables:



users



price\_history



deals



notifications



settings



\---



\# Logging



Log every scan.



Log notifications.



Log failures.



Log scheduler execution.



\---



\# Deployment



Docker



GitHub Actions



Oracle Cloud Ready



\---



\# Future Features



Explore Everywhere



Cheapest Month



Flexible Dates



Google Flights Provider



Kiwi Provider



React Dashboard



REST API



Weather



Visa Information



Travel Budget



Hotel Suggestions



AI Recommendation Engine



\---



\# Non Functional Requirements



Use SOLID



Use Clean Architecture



Use Dependency Injection



Type hints everywhere



Write unit tests



No duplicated code



No hardcoded secrets



Production quality code only

