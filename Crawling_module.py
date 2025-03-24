# =============================================================================
# 숏/롱 구분해서 오늘 날짜 필터링 / 광고 유무 확인을 위한 모듈들이 저장된 코드
# =============================================================================

import datetime
import pygsheets
import json
import requests
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from selenium import webdriver
from selenium.webdriver.common.by import By
import pandas as pd

# =============================================================================
#                         필요한 함수 정의 코드
# =============================================================================

class Need_utils():

    def __init__(self, api) :
        self.api = api

    @staticmethod
    def get_channel_ids(gcp_key_path, gsheet_id, sheet_name):
        gc = pygsheets.authorize(service_account_file=gcp_key_path)
        sheet = gc.open_by_key(gsheet_id)
        wks = sheet.worksheet_by_title(sheet_name)
        channel_ids = wks.get_col(3)[3:]  # 첫 번째 행은 헤더

        return [id for id in channel_ids if id]  # channel id 바로 리스트화
    
    def is_this_ad(self, video_id):
        youtube = build('youtube', 'v3', developerKey=self.api)
        request = youtube.videos().list(
            part='paidProductPlacementDetails',
            id=video_id
        )
        response = request.execute()
        
        return response['items'][0]['paidProductPlacementDetails']['hasPaidProductPlacement']
    
    @staticmethod
    def get_today_date():
        # return datetime.datetime.now().date().strftime('%Y-%m-%d')
        return (datetime.datetime.now() - datetime.timedelta(days=2)).date().strftime('%Y-%m-%d')


# =============================================================================
#                         Short_video_extract 코드
# =============================================================================


class Short_video_extract:
    # 객체 정의
    def __init__(self, today):
        self.today = today
        self.today_true_video = []
    
    def for_shorts_info_get(self, short_channel_ucid, Pre_Function):
        today_shorts_video = []
            
        response = requests.get(f'https://www.youtube.com/channel/{short_channel_ucid}/shorts')
        # BeautifulSoup으로 HTML 파싱
        soup = BeautifulSoup(response.text, "html.parser")

        # ytInitialData 추출
        script_tag = soup.find('script', string=lambda text: text and 'var ytInitialData' in text)
        if script_tag is None:
            print(f"Error: ytInitialData not found for channel {short_channel_ucid}")
            return []    # 빈 리스트 반환

        # JSON 데이터 파싱
        try:
            json_text = script_tag.string.strip().split(' = ', 1)[1].rsplit(';', 1)[0]
            data = json.loads(json_text)
            tabs = data['contents']['twoColumnBrowseResultsRenderer']['tabs']
        except Exception as e:
            print(f"Error parsing JSON for channel {short_channel_ucid}: {e}")
            return []   # 빈 리스트 반환

        # shorts id 저장
        for tab in tabs:
            tab_renderer = tab.get('tabRenderer', {})
            content = tab_renderer.get('content', None)
            if content is not None:  # content가 none이 아니라면 멈추기
                break
            
        # 가져왔으니까 이제 그 내부 파악하기
        under1 = content.get('richGridRenderer', {}).get('contents', [])
        found = False  # 해당 채널에 영상이 있는지 여부
        for under2 in under1:
            rich_content = under2.get('richItemRenderer', {}).get('content', {})
            found = True
            if 'shortsLockupViewModel' in rich_content:
                entityid = rich_content.get('shortsLockupViewModel', {})
                short_video_id = entityid.get('entityId', '').replace('shorts-shelf-item-', '')
                # 첫 번째 영상 처리: 오늘 날짜 여부 확인
                today_date, is_today, title = self.today_shorts(self.today, short_video_id)

                print('today_date :', today_date)
                print('title :', title)
                if is_today:  # is_today가 True면 
                    today_shorts_video.append(today_date)
                    
                    ad_or_not = Pre_Function.is_this_ad(short_video_id)
                    self.today_true_video.append({
                        "video_id": f'[S]_{short_video_id}',
                        "text": title,
                        "ad": ad_or_not
                    })
                    
                else:
                    # 오늘 날짜가 아닌 경우, 해당 채널의 검사를 중단
                    break
        
        if not found:
            print(f"{short_channel_ucid} : 이 채널의 숏츠 영상은 찾지 못 했어요. 1. 숏츠가 없거나 2. HTML 구조가 다르다 ..")
                
        # 모든 채널 처리 후 누적 결과 반환
        return self.today_true_video
    

    def today_shorts(self, today, short_video_id=None):
        driver = webdriver.Chrome()
        try:
            url = f"https://www.youtube.com/shorts/{short_video_id}"  # 하나씩 아이디가 들어감
            driver.get(url)

            page_manager = driver.find_element(By.ID, 'watch7-content')
            # ytd-page-manager의 HTML 가져오기
            page_manager_html = page_manager.get_attribute('outerHTML')
            date_soup = BeautifulSoup(page_manager_html, "html.parser")
            meta_date = date_soup.find("meta", {"itemprop": "uploadDate"})
            date_text = meta_date.get('content', '')
            date = pd.to_datetime(date_text[:10]).strftime('%Y-%m-%d') if date_text else None

            print(date)

            if today == date:
                head_element = driver.find_element(By.TAG_NAME, 'head')
                head_html = head_element.get_attribute('outerHTML')
                head_soup = BeautifulSoup(head_html, "html.parser")
                title = head_soup.find("title").text
                title = title.split(" - ")[0]
                return date, True, title  # 오늘 날짜이면 (date, True, title) 반환
            else:
                title = None
                return date, False, title
        except Exception as e:
            print(f"Error processing video {short_video_id}: {e}")
            return None, False, None  # 항상 튜플 반환
        finally:
            driver.quit()


# =============================================================================
#                         Long_video_extract 코드
# =============================================================================


class Long_video_extract:
    # 객체 정의
    def __init__(self, today, today_true_video):
        self.today = today
        self.today_true_video = today_true_video

    def for_long_info_get(self, long_ucid, Pre_Function):
        today_longs_video = []

        response = requests.get(f'https://www.youtube.com/channel/{long_ucid}/videos')
        # BeautifulSoup으로 HTML 파싱
        soup = BeautifulSoup(response.text, "html.parser")

        # ytInitialData 추출
        script_tag = soup.find('script', string=lambda text: text and 'var ytInitialData' in text)

        try:
            # JSON 데이터 파싱
            json_text = script_tag.string.strip().split(' = ', 1)[1].rsplit(';', 1)[0]
            data = json.loads(json_text)
            tabs = data['contents']['twoColumnBrowseResultsRenderer']['tabs']
        except Exception as e:
            print(f"Error parsing JSON for channel {long_ucid}: {e}")
            return []  # 빈 리스트 반환

        # long id 저장
        long_ids = []
        for tab in tabs:
            tab_renderer = tab.get('tabRenderer', {})
            content = tab_renderer.get('content', None)
            if content is not None:
                break

        # 가져왔으니까 이제 그 내부 파악하기
        under1 = content.get('richGridRenderer', {}).get('contents', [])
        found = False
        for under2 in under1:
            rich_content = under2.get('richItemRenderer', {}).get('content', {})
            found = True
            if 'videoRenderer' in rich_content:
                video_render = rich_content.get('videoRenderer', {})
                long_video_id = video_render.get('videoId', {})
                long_ids.append(long_video_id)

                today_date, is_today, description = self.today_longs(self.today, long_video_id)
                if is_today:  # is_today가 True가 반환됐다면 
                    today_longs_video.append(today_date)
                    print('today_date :', today_date)

                    ad_or_not = Pre_Function.is_this_ad(long_video_id)
                    self.today_true_video.append({
                        "video_id": f'[L]_{long_video_id}',
                        "text": description,
                        "ad": ad_or_not
                    })
                else:
                    break

        if not found:  # 해당 채널에 영상이 아예 없다면
            print(f"{long_ucid} : 이 채널의 숏츠 영상은 찾지 못 했어요. 1. 숏츠가 없거나 2. HTML 구조가 다르다 ..")

        # 모든 채널 처리 후 누적 결과 반환
        return self.today_true_video

    def today_longs(self, today, long_video_ids=None):
        driver = webdriver.Chrome()
        try:
            url = f"https://www.youtube.com/watch?v={long_video_ids}"  # 하나씩 아이디가 들어감
            driver.get(url)

            page_manager = driver.find_element(By.ID, 'watch7-content')
            # ytd-page-manager의 HTML 가져오기
            page_manager_html = page_manager.get_attribute('outerHTML')
            date_soup = BeautifulSoup(page_manager_html, "html.parser")
            meta_date = date_soup.find("meta", {"itemprop": "uploadDate"})
            date_text = meta_date.get('content', '')
            date = pd.to_datetime(date_text[:10]).strftime('%Y-%m-%d') if date_text else None

            if today == date:
                page_manager = driver.find_element(By.ID, 'page-manager')
                # ytd-page-manager의 HTML 가져오기
                page_manager_html = page_manager.get_attribute('outerHTML')
                soup = BeautifulSoup(page_manager_html, "html.parser")
                microformat = soup.find("div", {"id": "microformat"})
                tags = microformat.find("script", {"type": "application/ld+json"})

                if tags:
                    data = json.loads(tags.string)
                    description = data.get("description", "")  # description 값 추출

                return date, True, description  # date값과 True, description 반환
            else:
                description = None
                return date, False, description
        except Exception as e:
            print(f"프로세싱 중 오류가 발생했어요 ... 이 놈입니다 -> {long_video_ids} 에러메세지 입니다 : {e}")
            return None, False, None  # 항상 튜플 반환
        finally:
            driver.quit()
