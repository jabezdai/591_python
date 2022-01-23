import time
import random
from typing import List
from urllib.parse import urlparse, parse_qs
import joblib
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from bs4 import BeautifulSoup




def main(
    output_path,start_pages, max_pages, quiet
):
    URL = "https://rent.591.com.tw/?kind=0&region=8&firstRow="+str(start_pages*30)+"&totalRows=12617"
    output_path = "cache/listings"+str(start_pages)+".jbl"
    try:
        region = parse_qs(urlparse(URL).query)["region"][0]
    except AttributeError as e:
        print("The URL must have a 'region' query argument!")
        raise e
    options = webdriver.ChromeOptions()
    if quiet:
        options.add_argument("headless")
    browser = webdriver.Chrome(options=options)
    browser.get(URL)
    try:
        browser.find_element_by_css_selector('dd[data-id='+region+']').click()
    except NoSuchElementException:
        pass
    time.sleep(2)
#    listings = List[str]
    listings = []
    for i in range(start_pages,max_pages):
        print("Page"+str(i+1))
        soup = BeautifulSoup(browser.page_source, "lxml")
        for item in soup.find_all("section", attrs={"class": "vue-list-rent-item"}):
            link = item.find("a")
            #print(link.attrs["href"].split("-")[-1].split(".")[0])
            listings.append(link.attrs["href"].split("-")[-1].split(".")[0])
            #print(listings)
            
        browser.find_element_by_class_name("pageNext").click()
        time.sleep(random.random() * 5)
        try:
            browser.find_element_by_css_selector("a.last")
            break
        except NoSuchElementException:
            pass
    print(len(set(listings)))
    joblib.dump(listings, output_path)
    #print("Done! Collected"+len(listings)+"entries.")


if __name__ == "__main__":
    for i in range(315,420,105):
        main("cache/listings.jbl",i,i+105,False)
