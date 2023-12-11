#!/usr/bin/env python3
# -*-coding:utf-8 -*-

import os
import sys
import datetime
import time
import pickle
from pathlib import Path
from io import StringIO
from typing import List
from logzero import logger
from selenium.webdriver.common.by import By
from selenium.common.exceptions import WebDriverException, ElementClickInterceptedException
import pandas as pd
from . import config
from . import chromedriver

SLEEP_SEC = 2
HOME_URL = 'https://moneyforward.com/'
SIGN_IN_URL = 'https://moneyforward.com/sign_in'
HISTORY_URL = 'https://moneyforward.com/bs/history'
EXPENSES_URL = 'https://moneyforward.com/cf'
SUMMARY_URL = 'https://moneyforward.com/cf/summary'


class MoneyforwardDriver:
    def __init__(self, cookie_path: str = '', download_path: str = '', debug: bool = False):

        download_dir_verified = download_path \
            if Path(download_path).is_dir() \
            else ''
        self.driver = chromedriver.init(
            headless=(not debug), download_dir=download_dir_verified)
        self.driver.implicitly_wait(10)
        self.__cookie_path = Path(cookie_path) if cookie_path else None
        self.__download_dir = download_dir_verified
        return

    def __del__(self):
        self.driver.quit()

    def login(self) -> bool:
        """マネーフォワードにログインする

        Returns:
            bool: ログインに成功した場合True, 失敗した場合False
        """
        logger.info('Trying to login with cookie.')
        is_success = self.__login_with_cookie() or self.__login_with_email()
        if is_success:
            logger.info('Login succeeded.')
        else:
            logger.error('Login Failed.')
        return is_success

    def __login_with_email(self) -> bool:
        if (not config.MF_EMAIL) or (not config.MF_PASSWORD):
            logger.error('MF_EMAIL or MF_PASSWORD is not set.')
            return False

        self.driver.get(SIGN_IN_URL)

        # メールアドレス入力画面
        logger.info('Current URL: %s', self.driver.current_url)
        self.driver.find_element(
            By.XPATH, '//input[@name="mfid_user[email]"]').send_keys(config.MF_EMAIL)
        self.driver.find_element(By.CSS_SELECTOR, 'button#submitto').click()

        # パスワード入力画面
        logger.info('Current URL: %s', self.driver.current_url)
        self.driver.find_element(
            By.XPATH, '//input[@name="mfid_user[password]"]').send_keys(config.MF_PASSWORD)
        self.driver.find_element(By.CSS_SELECTOR, 'button#submitto').click()

        self.driver.get(HISTORY_URL)
        time.sleep(SLEEP_SEC)
        if self.driver.current_url != HISTORY_URL:
            return False
        else:
            # Cookieに保存する
            if (self.__cookie_path):
                pickle.dump(self.driver.get_cookies(),
                            open(self.__cookie_path, 'wb'))
            return True

    def __login_with_cookie(self) -> bool:
        if self.__cookie_path is None:
            return False
        if (not self.__cookie_path.exists()):
            logger.info('Cookie does not exist.')
            return False

        # Cookieの復元
        # 一旦ドメインが一致するサイトを呼ぶことでadd_cookieが復元できる
        self.driver.get(HISTORY_URL)
        cookies = pickle.load(open(self.__cookie_path, 'rb'))
        for cookie in cookies:
            if 'expiry' in cookie:
                cookie.pop('expiry')
            self.driver.add_cookie(cookie)

        # ログイン実行
        self.driver.get(HISTORY_URL)
        time.sleep(SLEEP_SEC)
        # ここではmoneyforwardのtopページが出る
        logger.info('Current URL: %s', self.driver.current_url)

        # ログインの確認のため、資産推移のページに遷移する。
        # ログインに失敗している場合、資産推移のページが表示されない。
        self.driver.get(HISTORY_URL)
        time.sleep(SLEEP_SEC)
        logger.info('Current URL: %s', self.driver.current_url)
        return (self.driver.current_url == HISTORY_URL)

    def update(self) -> None:
        """すべての口座を更新する
        """
        try:
            self.driver.get('https://moneyforward.com/accounts')
            elms = self.driver.find_elements(By.XPATH,
                                             "//input[@data-disable-with='更新']")
            for i, elm in enumerate(elms):
                logger.info('Updating account... [%d/%d]', i+1, len(elms))
                elm.click()
                time.sleep(0.5)
        except WebDriverException as e:
            logger.error(e, file=sys.stderr)
        else:
            logger.info('Update finished.')
        time.sleep(SLEEP_SEC)
        return

    def input_expense(self, category: str, subcategory: str, date: str, amount: int, content: str = ''):
        """支出を入力する

        Args:
            category (str): 大項目
            subcategory (str): 中項目
            date (str): 支出日
            amount (int): 金額
            content (str, optional): 内容(任意). Defaults to ''.
        """
        if self.driver.current_url != EXPENSES_URL:
            self.driver.get(EXPENSES_URL)

        try:
            # 入力欄を開く
            self.driver.find_element(
                By.CSS_SELECTOR, 'button.cf-new-btn.btn.modal-switch.btn-warning').click()
            # 入力
            self.driver.find_element(
                By.XPATH, '//*[@id="appendedPrependedInput"]').send_keys(amount)
            self.__select_category(category)
            self.__select_subcategory(subcategory)
            self.__input_date(date)
            if content:
                self.driver.find_element(
                    By.XPATH, '//*[@id="js-content-field"]').send_keys(content)
            # 送信
            self.driver.find_element(
                By.XPATH, '//*[@id="submit-button"]').click()
            # 閉じる
            self.driver.find_element(
                By.XPATH, '//*[@id="cancel-button"]').click()
        except WebDriverException as e:
            logger.error(e)
            return False
        except IndexError:
            logger.error(
                "The specified categories are invalid. Category: %s, Subcategory: %s", category, subcategory)
            return False
        else:
            logger.info('Successfully input expense data: %s %s \\%d on %s',
                        category, subcategory, amount, date)
            return True

    def __select_category(self, category: str):
        self.driver.find_element(
            By.XPATH, '//*[@id="js-large-category-selected"]').click()
        li = self.driver.find_element(
            By.CSS_SELECTOR, '.dropdown-menu.main_menu.minus')
        [a for a in li.find_elements(By.CLASS_NAME, "l_c_name") if a.get_attribute(
            "innerHTML") == category].pop().click()

    def __select_subcategory(self, subcategory: str):
        self.driver.find_element(
            By.XPATH, '//*[@id="js-middle-category-selected"]').click()
        li = self.driver.find_element(
            By.CSS_SELECTOR, '.dropdown-menu.sub_menu')
        [a for a in li.find_elements(By.CLASS_NAME, "m_c_name") if a.get_attribute(
            "innerHTML") == subcategory].pop().click()

    def __input_date(self, date: str):
        elm_date_input = self.driver.find_element(
            By.XPATH, '//*[@id="updated-at"]')
        elm_date_input.clear()
        elm_date_input.send_keys(date)

    def download_monthly_assets(self, year: int, month: int):
        """月次の資産をCSVファイルとしてダウンロードする

        インスタンスの生成時に引数`download_path`として適切なパスが指定されていない場合、ダウンロードを行わない

        Args:
            year (int): 年
            month (int): 月
        """
        if (not self.__download_dir):
            logger.error('The download directory is invalid.')
            return
        logger.info('Downloading an asset data for %d/%d.', year, month)
        date = f'{year}-{month:02d}-01'
        try:
            self.driver.get(
                f'https://moneyforward.com/bs/history/list/{date}/monthly/csv')
            time.sleep(0.5)
        except WebDriverException as e:
            logger.error(e)
        else:
            logger.info('Download completed.')
        time.sleep(SLEEP_SEC)
        return

    def fetch_monthly_income_and_expenses(self, year: int, month: int) -> List[pd.DataFrame]:
        """指定した月の収入と支出を取得する

        Args:
            year (int): 年
            month (int): 月

        Returns:
            List[pd.DataFrame]: 収入と支出のテーブル。該当月の支出データがない場合、支出はNoneとなる
        """
        target_date = self.__validate_date(year, month)
        if target_date is None:
            return None

        self.driver.get(SUMMARY_URL)
        time.sleep(SLEEP_SEC)
        self.__select_month(target_date)
        expenses = self.__read_monthly_expenses()
        income = self.__read_monthly_income()
        return [income, expenses]

    def fetch_monthly_income_and_expenses_since(self, year: int, month: int) -> List[pd.DataFrame]:
        """指定した月から現在までの収入と支出を取得する

        Args:
            year (int): 年
            month (int): 月

        Returns:
            List[pd.DataFrame]: 収入と支出のテーブル
                - 0: 収入
                - 1: 支出
        """
        target_date = self.__validate_date(year, month)
        if target_date is None:
            return None

        self.driver.get(SUMMARY_URL)
        time.sleep(SLEEP_SEC)
        concatted_expenses_table = None
        concatted_income_table = None
        while True:
            displayed_date = self.__get_date()
            logger.info('Fetching income and expenses on %s.', displayed_date)

            income = self.__read_monthly_income()
            concatted_income_table = pd.concat(
                [income, concatted_income_table])

            expenses = self.__read_monthly_expenses()
            concatted_expenses_table = pd.concat(
                [expenses, concatted_expenses_table]) if expenses is not None else concatted_expenses_table

            if displayed_date == target_date:
                break

            try:
                self.__get_previous_month_button().click()
            # 非プレミアムで1年以上前に戻るとクリックできなくなる
            except ElementClickInterceptedException as e:
                logger.warning(e, file=sys.stderr)
                break
            time.sleep(SLEEP_SEC)
        return [concatted_income_table.reset_index(drop=True), concatted_expenses_table.reset_index(drop=True)]

    def __validate_date(self, year: int, month: int) -> str:
        try:
            input_date = datetime.date(year, month, 1)
        except ValueError as e:
            logger.warning(e)
            return None
        if input_date > datetime.date.today():
            logger.warning('The specified date must be before today.')
            return None
        return input_date.strftime('%Y/%m/%d')

    def __select_month(self, target_date: str) -> bool:
        previous_month_button = self.__get_previous_month_button()
        displayed_date = self.__get_date()
        while (True):
            if (displayed_date == target_date):
                return True
            try:
                previous_month_button.click()
            except ElementClickInterceptedException as e:
                logger.warning(e, file=sys.stderr)
                return False
            time.sleep(SLEEP_SEC)
            displayed_date = self.__get_date()

    def __get_previous_month_button(self):
        if self.driver.current_url == SUMMARY_URL:
            return self.driver.find_element(By.XPATH, '//a[@id="b_range"]')
        else:
            return None

    def __get_date(self) -> str:
        if self.driver.current_url == SUMMARY_URL:
            return self.driver.find_element(By.CLASS_NAME, 'from-to').text[:10]
        else:
            return None

    def __read_monthly_expenses(self) -> pd.DataFrame:

        elm = self.driver.find_element(
            By.XPATH, '//*[@id="cache-flow"]/div[3]/table')
        table_html = elm.get_attribute("outerHTML")
        df = pd.read_html(StringIO(table_html.replace('円', '')), thousands=',')

        if len(df) > 1:  # 該当月の支出データがある場合
            formatted_table = self.__format__table(df[1], self.__get_date())
            return formatted_table
        else:   # 該当月の支出データがない場合
            return None

    def __read_monthly_income(self) -> pd.DataFrame:
        elm = self.driver.find_element(
            By.XPATH, '//*[@id="monthly_total_table"]')
        table_html = elm.get_attribute("outerHTML")
        df = pd.read_html(
            StringIO(table_html.replace('円', '')), thousands=',')[0]
        income = df['当月収入'][0]
        displayed_date = self.__get_date()
        income_df = pd.DataFrame(
            [[displayed_date, income]], columns=['日付', '収入'])
        return income_df

    def __format__table(self, df: pd.DataFrame, date: str) -> pd.DataFrame:
        """収支内訳から取得したテーブルを整形する

        引数として渡されているテーブルは以下のような形式のため、"食費 合計"などと書かれた行からは
        [項目](この場合"食費")を取得する。
        それ以外の行では項目名を[小項目], 金額を[金額]として取得する。

        項目          金額
        食費 合計      19292
        食料品        16267
        外食          3025
        日用品 合計    4232
        ドラッグストア  4232
        衣服・美容 合計 800
        衣服          800

        Args:
            df (pd.DataFrame): 収支内訳から取得したテーブル
            date (str): 取得したテーブルの日付

        Returns:
            pd.DataFrame: 整形後のテーブル
        """
        l_data = []
        for index, row in df.iterrows():
            if '合計' in row['項目']:
                category = row['項目'].replace(' 合計', '')
                continue
            sub_category = row['項目']
            amount = row['金額']
            l_data.append([date, category, sub_category, amount])
        return pd.DataFrame(l_data, columns=['日付', '項目', '小項目', '金額'])
