import base64
import calendar
import itertools
import warnings
from datetime import datetime, timedelta
from io import BytesIO

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import statsmodels.api as sm
from django.core.cache import cache
from django.shortcuts import render
from matplotlib.figure import Figure
from rest_framework import generics, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.urls import reverse
from CurrencyExchange.settings import BASE_DIR


# def delete_cache(request):
#     cache_key = request.POST.get("cache_key","")
#     cache.delete(cache_key)
#     print("yo")
#     return Response(data={"cached_data": cache.get(self.__cache_key)})


class CurrencyPrediction(generics.CreateAPIView):
    """
    Initializing all the instance variables to be used during exceution.
    """

    def __init__(self):
        self.__cache_key = ""
        self.__base_currency = ""
        self.__target_currency = ""
        self.__raw_json_data = None
        self.__cached_data = None
        self.__todays_date = datetime.now().date()
        self.__cache_key = "historical_data"

    """
    To set the cache memory with the data of the external API call through a fixed key
    """

    def set_cache(self, set_data):
        cache.set(self.__cache_key, set_data, None)

    """
    To retrieve the cache data from the memcached Django server by the fixed key
    """

    def get_cache(self):
        cached_data = cache.get(self.__cache_key)
        return cached_data

    """
    Using the requests library a get request is made for the exchange API rates
    """

    def url_request(self, url):
        return requests.get(url=url).json()

    """
    API call to delete the cache, only to be done by the admin
    """
    def get(self, request):
        # self.delete_cache()
        print("image is here")
        # return Response(data={"cached_data": self.get_cache()})
        return render(request,'PredictRateApp/show_result.html',status=status.HTTP_200_OK)

    """
    Deletes the cache by invoking the delete function of the django cache library through fixed key
    """

    def delete_cache(self):
        cache.delete(self.__cache_key)

    """
    Checks whether the input data from the post request is erroneous or not and returns HTTP_400_BAD_REQUEST if erroneous.
    """
    def check_input_data(self, start_date, max_waiting_time, amount):
        if((not isinstance(max_waiting_time, int)) or (start_date < self.__todays_date) or (max_waiting_time < 0) or (amount < 0 or not isinstance(amount, int))):
            return True

    """
    Sorts the dictionary of the exchange rate api data and sorts it in ascending order of the dates.
    """
    def sort_dict(self, unsorted_list):
        ordered_data = sorted(unsorted_list.items(), key=lambda x: datetime.strptime(
            x[0], '%Y-%m-%d'), reverse=False)
        return dict(ordered_data)

    """
    Initial API call to load the cache data for the first time or when deleted by the admin.
    """

    def stock_exchange_api(self):

        before_2_months = self.__todays_date - timedelta(days=60)
        raw_url = "https://api.exchangeratesapi.io/history?start_at="+str(before_2_months)+"&end_at="+str(
            self.__todays_date)+"&base="+self.__base_currency+"&symbols="+self.__target_currency
        self.__raw_json_data = self.url_request(raw_url)
        self.__raw_json_data['rates'] = self.sort_dict(
            self.__raw_json_data['rates'])

    """
    To check whether the start date or end date is sunday or saturday as the exchange rates are not available for the following days.
    """
    def check_sunday_saturday(self, date):

        if(date.strftime("%A") == 'Sunday'):
            return date - timedelta(days=2)
        elif(date.strftime("%A") == 'Saturday'):
            return date - timedelta(days=1)
        else:
            return date

    """
    Uses ARIMA model to forecast the exchange rates and saves the forecasts in the forecasted_graphs folder in the project directory.
    """
    def chart_creation(self, start_date, max_waiting_time):
        end_date = start_date + timedelta(days=int(max_waiting_time))
        start_date = self.check_sunday_saturday(start_date)
        end_date = self.check_sunday_saturday(end_date)

        all_data = self.get_cache()
        rates = all_data['rates']
        dates = []
        symbol_values = []
        for key, value in rates.items():
            temp = '%.2f' % value['INR']
            dates.append(key)
            symbol_values.append(temp)
        df = pd.DataFrame(symbol_values, index=dates,
                          columns=['rate'])
        df['rate'] = df['rate'].astype('float32')
        df.sort_index(inplace=True)
        df = df.fillna(df.bfill())
        mod = sm.tsa.statespace.SARIMAX(df,
                                        order=(1, 1, 1),
                                        enforce_stationarity=False,
                                        enforce_invertibility=False)

        results = mod.fit()
        pred = results.get_prediction(
            start=start_date, end=end_date, dynamic=False)
        fig = Figure()
        ax = fig.subplots()
        ax.plot(pred.predicted_mean)
        buf = BytesIO()
        fig.savefig(BASE_DIR+"/forecasted_graphs/buf.png", format="png")

    """
    To check whether the cache is present or not and if present than has to be updated by how many days.
    So call to exchangeratesapi is made accordingly
    """

    def cache_check(self):
        if self.__cached_data is None:

            self.stock_exchange_api()
            self.set_cache(self.__raw_json_data)
            self.__cached_data = self.get_cache()

        elif((self.__todays_date - datetime.strptime(self.__cached_data['end_at'], '%Y-%m-%d').date()) == timedelta(days=1)):

            date = self.__todays_date + timedelta(days=1)
            raw_url = "https://api.exchangeratesapi.io/" + \
                str(date)+"?base=USD&symbols=INR"
            data_new = self.url_request(raw_url)
            self.__cached_data['rates'][data_new['date']] = data_new['rates']
            self.__cached_data['end_at'] = str(self.__todays_date)
            self.__cached_data['rates'].pop()
            self.set_cache(self.__cached_data)

        elif((self.__todays_date - datetime.strptime(self.__cached_data['end_at'], '%Y-%m-%d').date()) >= timedelta(days=1)):

            days = self.__todays_date - \
                datetime.strptime(
                    self.__cached_data['end_at'], '%Y-%m-%d').date()
            before_date = self.__todays_date - timedelta(days=((days.days)-1))
            raw_url = "https://api.exchangeratesapi.io/history?start_at="+str(before_date)+"&end_at="+str(
                self.__todays_date)+"&base="+self.__base_currency+"&symbols="+self.__target_currency
            data_new = self.url_request(raw_url)
            self.__cached_data['rates'].update(data_new['rates'])
            self.__cached_data['end_at'] = str(self.__todays_date)
            self.set_cache(self.__cached_data)

    """
    Handles the request and acts as a driver function to cache_check(), check_input_data(), chart_creation().
    Thus, creating a forecast for the exchange rates.
    """
    def post(self, request):
        self.__base_currency = request.data.get("base_currency", "")
        self.__target_currency = request.data.get("target_currency", "")
        amount = request.data.get("amount", "")
        max_waiting_time = request.data.get("max_waiting_time", "")
        start_date = request.data.get("start_date", "")

        self.__cached_data = self.get_cache()
        self.cache_check()
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        if (self.check_input_data(start_date, max_waiting_time, amount)):
            return Response(data={"Value error": "Start Date should be a future date, Amount/Max Waiting Time should not be negative and should be an Integer"}, status=status.HTTP_400_BAD_REQUEST)

        self.chart_creation(start_date, max_waiting_time)
        url = reverse('show_result')
        print("first")
        return Response(data={"url":url,"cache":self.get_cache()},status=status.HTTP_200_OK)

class DeleteCache(generics.CreateAPIView):

    """
    Deletes the cache when provided by the cache_key corresponding to the cache memory.
    """
    def post(self,request):
        cache_key = request.data.get("cache_key","")
        cache.delete(cache_key)

        return Response(data={"cached_data": cache.get(cache_key)})
