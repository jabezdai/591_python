import re
import time
import shutil
import random
import logging
from datetime import date
from typing import Optional

import joblib
import pandas as pd
from tqdm import tqdm
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from tenacity import (
    retry,
    stop_after_attempt,
    wait_fixed,
    before_sleep_log,
    RetryError,
    retry_if_exception_type,
)

from utils.post_processing import adjust_price_, auto_marking_, parse_price

LOGGER = logging.getLogger(__name__)
filenum = 0


class NotExistException(Exception):
    pass


def get_attributes(soup):
    result = {}
    try:
        if "限女" in soup.select_one("div.service-rule").text:
            result["性別"]="限女"
        elif "限男" in soup.select_one("div.service-rule").text:
            result["性別"]="限男"
        else:
            result["性別"]="無限制"
    except AttributeError:
        result["性別"] = "請參閱網站"
    contents = soup.select_one("div.main-info-left div.content").children
    for item in contents:
        try:
            name = item.select_one("div div.name").text
            if name in ("租金含", "車位費", "管理費"):
                result[name] = name = item.select_one("div div.text").text.strip()
        except AttributeError as e:
            print(e)
            continue
    service_list = soup.select_one("div.service-list-box").select(
        "div.service-list-item"
    )
    services = []
    for item in service_list:
        if "del" in item["class"]:
            continue
        services.append(item.text.strip())
    result["提供設備"] = ", ".join(services)
    attributes = soup.select_one("div.house-pattern").find_all("span")
    for i, key in enumerate(("格局", "坪數", "樓層", "型態")):
        result[key] = attributes[i * 2].text.strip()
    return result


@retry(
    reraise=False,
    retry=retry_if_exception_type(TimeoutException),
    stop=stop_after_attempt(2),
    wait=wait_fixed(1),
    before_sleep=before_sleep_log(LOGGER, logging.INFO),
)
def get_page(browser: webdriver.Chrome, listing_id):
    browser.get("https://rent.591.com.tw/home/"+listing_id.strip())
    print("https://rent.591.com.tw/home/"+listing_id.strip())
    wait = WebDriverWait(browser, 5)
    try:
        wait.until(
            ec.visibility_of_element_located((By.CSS_SELECTOR, "div.main-info-left"))
        )
    except TimeoutException as e:
        soup = BeautifulSoup(browser.page_source, "lxml")
        tmp = soup.select_one("div.title")
        # print(tmp)
        if tmp and "不存在" in tmp.text:
            raise NotExistException()
        else:
            raise e
    return True


def get_listing_info(browser: webdriver.Chrome, listing_id):
    try:
        get_page(browser, listing_id)
    except RetryError:
        pass
    soup = BeautifulSoup(browser.page_source, "lxml")
    result = {"id": listing_id}
    result["title"] = soup.select_one(".house-title h1").text
    phone = soup.find_all(class_="tel-txt", string=re.compile("^09\d{2}(\d{6}|-\d{3}-\d{3})"))

    result["phone"]=str(phone)[23:35]

    result["addr"] = soup.select_one("span.load-map").text.strip()
    complex = soup.select_one("div.address span").text.strip()
    if complex != result["addr"]:
        result["社區"] = complex
    result["price"] = parse_price(soup.select_one("span.price").text)
    result["desc"] = soup.select_one("div.article").text.strip()
    result["poster"] = re.sub(r"\s+", " ", soup.select_one("p.name").text.strip())
    result.update(get_attributes(soup))
    print(result)

    return result


def main(
    source_path: str = "cache/listings"+str(filenum)+".jbl",
    data_path: Optional[str] = None,
    output_path: Optional[str] = None,
    limit: int = 105,
    headless: bool = False,
):
    
    
    listing_ids = joblib.load(source_path)
    df_original = Optional[pd.DataFrame]# = None
    if data_path:
        if data_path.endswith(".pd"):
            df_original = pd.read_pickle(data_path)
        else:
            df_original = pd.read_csv(data_path)
        listing_ids = list(set(listing_ids) - set(df_original.id.values.astype("str")))
        print(len(listing_ids))

    if limit > 0:
        listing_ids = listing_ids[:limit]

    print("Collecting "+str(len(listing_ids))+" entries...")

    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("headless")
    prefs = {"profile.managed_default_content_settings.images": 2}
    options.add_experimental_option("prefs", prefs)
    browser = webdriver.Chrome(options=options)

    data = []
    for id_ in tqdm(listing_ids, ncols=100):
        try:
            data.append(get_listing_info(browser, id_))
        except NotExistException:
            LOGGER.warning("Does not exist: "+id_)
            pass
        time.sleep(random.random() * 5)

    df_new = pd.DataFrame(data)
    optional_fields = ("租金含", "車位費", "管理費")
    for field in optional_fields:
        if field not in df_new:
            df_new[field] = None
    df_new = auto_marking_(df_new)
    df_new = adjust_price_(df_new)
    df_new["fetched"] = date.today().isoformat()
    """
    if df_original is not None:
        df_new = pd.concat([df_new, df_original], axis=0).reset_index(drop=True)
"""
    if output_path is None and data_path is None:
        # default output path
        output_path = "cache/df_listings"+str(filenum)+".csv"
    elif output_path is None and data_path:
        output_path = data_path
        shutil.copy(data_path, data_path + ".bak")

    df_new["link"] = (
        "https://rent.591.com.tw/rent-detail-" + df_new["id"].astype("str") + ".html"
    )
    print("https://rent.591.com.tw/rent-detail-" + df_new["id"].astype("str") + ".html")
    column_ordering = [
        "mark",
        "title",
        "price",
        "price_adjusted",
        "link",
        "addr",
        "社區",
        "車位費",
        "管理費",
        "poster",
        "phone",
        "性別",
        "提供設備",
        "格局",
        "坪數",
        "樓層",
        "型態",
        "id",
        "fetched",
        "desc",
    ]
    print(df_new.drop("desc", axis=1).sample(min(df_new.shape[0], 10)))
    df_new[column_ordering].to_csv(output_path, index=False, encoding='utf-8-sig')
    print("Finished!")
    browser.close()


if __name__ == "__main__":
    main()
