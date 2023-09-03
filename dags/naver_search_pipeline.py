from datetime import datetime
from airflow import DAG
import json

import sys
sys.path.extend("./")

from preprocess.naver_preprocess import preprocessing

from airflow.providers.sqlite.operators.sqlite import SqliteOperator
from airflow.providers.http.sensors.http import HttpSensor
from airflow.providers.http.operators.http import SimpleHttpOperator
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.operators.email import EmailOperator

default_args = {
    "start_date": datetime(2021, 1, 1)
}

NAVER_CLI_ID = "WCP5cyMbrVApM3coS753"
NAVER_CLI_SECRET = "Y1RytrBRmj"

def _complete():
    print("네이버 검색 DAG 완료")

# DAG 틀 설정
with DAG(
    dag_id="naver-search-pipeline",
    # crontab 표현 사용 가능 https://crontab.guru/
    schedule_interval="@daily", 
    default_args=default_args,
    # 태그는 원하는대로
    tags=["naver", "search", "local", "api", "pipeline"],
    # catchup을 True로 하면, start_date 부터 현재까지 못돌린 날들을 채운다
    catchup=False) as dag:

    # 네이버 API로 지역 식당을 검색할 것이다. 
    # 지역 식당명, 주소, 카테고리, 설명, 링크를 저장할 것이므로 다음과 같이 테이블을 구성한다.
    creating_table = SqliteOperator(
        task_id="creating_table",
        sqlite_conn_id="db_sqlite", # 웹UI에서 connection을 등록해줘야 함.
        # naver_search_result 라는 테이블이 없는 경우에만 만들도록 IF NOT EXISTS 조건을 넣어주자.
        sql='''
            CREATE TABLE IF NOT EXISTS naver_search_result( 
                title TEXT,
                address TEXT,
                category TEXT,
                description TEXT,
                link TEXT
            )
        '''
    )

    # HTTP 센서를 이용해 응답 확인 (감지하는 오퍼레이터로 실제 데이터를 가져오는 것 X)
    is_api_available = HttpSensor(
        task_id="is_api_available",
        http_conn_id="naver_search_api",
        endpoint="v1/search/local.json", # url - uri에서 Host 부분을 제외한 파트(~.com 까지가 host)
        # 요청 헤더, -H 다음에 오는 내용들
        headers={
            "X-Naver-Client-Id" : f"{NAVER_CLI_ID}",
            "X-Naver-Client-Secret" : f"{NAVER_CLI_SECRET}",
        },
        request_params={
            "query": "수제맥주",
            "display": 5
        }, # 요청 변수
        response_check=lambda response: (response.json()) # 응답 확인
    )

    crawl_naver = SimpleHttpOperator(
        task_id="crawl_naver",
        http_conn_id="naver_search_api",
        endpoint="v1/search/local.json", # url 설정
        headers={
            "X-Naver-Client-Id" : f"{NAVER_CLI_ID}",
            "X-Naver-Client-Secret" : f"{NAVER_CLI_SECRET}",
        }, # 요청 헤더
        data={
            "query": "수제맥주",
            "display": 5
        }, # 요청 변수
        method="GET", # 통신 방식 GET, POST 등등 맞는 것으로
        response_filter=lambda res : json.loads(res.text),
        log_response=True
    )

    preprocess_result = PythonOperator(
            task_id="preprocess_result",
            python_callable=preprocessing # 실행할 파이썬 함수
    )

    store_result = BashOperator(
        task_id="store_naver",
        bash_command='echo -e ".separator ","\n.import /root/airflow/dags/data/naver_processed_result.csv naver_search_result" | sqlite3 /root/airflow/airflow.db'
    )

    # 대그 완료 출력
    print_complete = PythonOperator(
            task_id="print_complete",
            python_callable=_complete # 실행할 파이썬 함수
    )

    # 파이프라인 구성하기
    creating_table >> is_api_available >> crawl_naver >> preprocess_result >> store_result >> print_complete