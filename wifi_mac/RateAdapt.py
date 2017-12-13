#!/usr/bin/env python
#
#  Created on: Mar 3, 2016
#      Author: haoyang

import random


class MinstrelController:
    """Minstrel algorithm"""

    def __init__(self, encoding_init, max_retry_counts=4, sample_ratio=10,
                 data_rate_table=None, log=False):
        """
        :param encoding_init: initial data rate
        :param max_retry_counts: maximum number of retries after failure
        :param sample_ratio: larger indicates faster adaptation (max 100)
        :param data_rate_table: throughput of each data rate
        """

        # Parameters
        if data_rate_table is None:
            data_rate_table = [6, 9, 12, 18, 24, 36, 48, 54]

        self.data_rate_table = data_rate_table
        self.SUPPORTED_DATA_RATES = len(data_rate_table)
        assert 0 <= encoding_init < self.SUPPORTED_DATA_RATES, "Incorrect initial data rate"
        self.MAX_RETRY_COUNT = max_retry_counts
        self.SAMPLE_RATIO = sample_ratio
        self.idx = encoding_init  # current data rate
        self.log = log

        print "======== Minstrel algorithm ======"
        print "Throughput table", self.data_rate_table
        print "No. of supporting data rates:", self.SUPPORTED_DATA_RATES
        print "Max retry count:", self.MAX_RETRY_COUNT
        print "SAMPLE_RATIO:", self.SAMPLE_RATIO
        print "Initial data rate: %d Mbps" % self.data_rate_table[self.idx]
        print "=================================="

        # Variables
        self.SAMPLE_COLUMNS = 10  # number of rows in sample table
        self.SAMPLE_STC = 4
        self.MAX_THR_RATES = 4  # number of highest throughput rates to consider

        self.sample_table = [[0xff] * self.SUPPORTED_DATA_RATES for x in
                             range(self.SAMPLE_COLUMNS)]  # [SAMPLE_COLUMNS]x[SUPPORTED_DATA_RATES];
        self.rate_statistic = [[0.0] * 8 for x in range(self.SUPPORTED_DATA_RATES)]  # [SUPPORTED_DATA_RATES]x[8];
        self.sample_statistic = [0] * self.SAMPLE_STC
        self.normal_tp_rate_table = [[0] * 3 for x in range(self.MAX_THR_RATES)]

        # Init sample_table
        for col in range(self.SAMPLE_COLUMNS):
            for i in range(self.SUPPORTED_DATA_RATES):
                rnd = random.randint(0, self.SUPPORTED_DATA_RATES - 1)
                new_idx = (i + rnd) % self.SUPPORTED_DATA_RATES
                while self.sample_table[col][new_idx] != 0xff:
                    new_idx = (new_idx + 1) % self.SUPPORTED_DATA_RATES
                self.sample_table[col][new_idx] = i

        # Init rate_tables
        for i in range(self.MAX_THR_RATES):
            # this is for normal rate: init max_hp: 7, second: 6, probe: 5 min: 0;
            self.normal_tp_rate_table[i][2] = self.MAX_THR_RATES

        self.lookaround_tp_rate_table = self.normal_tp_rate_table

        for i in range(self.SUPPORTED_DATA_RATES):
            self.rate_statistic[i][0] = i

        if self.log:
            self.show_rate_table()
            self.show_sample_table()
            self.show_sample_statistic()

    def data_sel(self, rate, success):
        return self.minstrel_update_stats(rate, success)

    def minstrel_update_stats(self, rate, success):
        # input minstrel_sta_info:  all date rates,data rates count
        self.idx = rate
        # increase sum packet counter
        self.sample_statistic[0] += 1

        # too many packets
        if self.sample_statistic[0] > 60000:
            self.sample_statistic[0:2] = 0

        delta = int(self.sample_statistic[0] * self.SAMPLE_RATIO / 100.0) - self.sample_statistic[1]

        # sample_statistic:
        # 0: total packets
        # 1: sample packets
        # 2: sample_row
        # 3: sample_colunm
        # sampling
        if delta > 0:
            self.idx = self.sample_table[self.sample_statistic[2]][self.sample_statistic[3]]
            self.sample_statistic[1] += 1
            self.sample_statistic[3] += 1
            if self.sample_statistic[3] == self.SUPPORTED_DATA_RATES:
                self.sample_statistic[3] = 0
                self.sample_statistic[2] += 1

            if self.sample_statistic[2] == self.SAMPLE_COLUMNS:
                self.sample_statistic[2] = 0

        # update rate_statistic:
        # 0: rate
        # 1: his_success
        # 2: his_attempts
        # 3: his_prob
        # 4: cur_success
        # 5: cur_attempts
        # 6: current_prob
        # 7: tp
        self.rate_statistic[self.idx][5] += 1  # ATTEMPT ++
        if success:
            self.rate_statistic[self.idx][4] += 1  # SUCCESS ++

        self.rate_statistic[self.idx][6] = int(
            self.rate_statistic[self.idx][4] * 100.0 / self.rate_statistic[self.idx][5])  # compute success probability

        if self.rate_statistic[self.idx][5] == self.MAX_RETRY_COUNT:  # attemps == MAXRETRY
            # avoid div 0
            if self.rate_statistic[self.idx][2] != 0:
                self.rate_statistic[self.idx][3] = int(
                    self.rate_statistic[self.idx][1] * 75.0 / self.rate_statistic[self.idx][2]
                    + self.rate_statistic[self.idx][4] * 75.0 / self.rate_statistic[self.idx][5])
            # too many packets
            if self.rate_statistic[self.idx][1] > 60000:
                self.rate_statistic[self.idx][1] = 0

            self.rate_statistic[self.idx][1] += self.rate_statistic[self.idx][4]
            self.rate_statistic[self.idx][2] += self.rate_statistic[self.idx][5]
            self.rate_statistic[self.idx][4] = 0
            self.rate_statistic[self.idx][5] = 0

        # Update throughput per rate, reset thr. below 10% success
        if self.rate_statistic[self.idx][6] < 10:
            self.rate_statistic[self.idx][7] = 0
        else:
            self.rate_statistic[self.idx][7] = self.rate_statistic[self.idx][6] * self.data_rate_table[self.idx]

        return self.sort_rate()

    def sort_rate(self):
        """
        Find the data rate that yields maximum throughput
        :return: the optimal data rate
        """
        tem_max_tp = 0
        tem_max_idx = 0
        for i in range(self.SUPPORTED_DATA_RATES):
            if self.rate_statistic[i][7] > tem_max_tp:
                tem_max_tp = self.rate_statistic[i][7]
                tem_max_idx = i
        return tem_max_idx
        # self.show_rate_table()

    def show_rate_table(self):
        if self.log:
            print "========== normal_tp_rate_table =========="
            print_matrix(self.normal_tp_rate_table)
            print "======== lookaround_tp_rate_table ========"
            print_matrix(self.lookaround_tp_rate_table)
            print "============= rate statistic ============"
            print_matrix(self.rate_statistic)
            print "=========================================="

    def show_sample_table(self):
        if self.log:
            print "============= sample table ==============="
            print_matrix(self.sample_table)

    def show_sample_statistic(self):
        if self.log:
            print "=========== sample_statistic ============"
            print_matrix(self.sample_statistic)

    def test(self):
        d = 0  # initial data rate
        for i in range(20):
            d = self.data_sel(d, True)
            print self.sample_statistic
            print d

        d = self.data_sel(d, False)
        print self.sample_statistic
        print d

        for i in range(650):
            d = self.data_sel(d, False)
            print self.sample_statistic
            print d

        for i in range(300):
            d = self.data_sel(d, True)
            print self.sample_statistic
            print d

        d = self.data_sel(d, True)
        print self.sample_statistic
        print d


class AarfController:
    def __init__(self, encoding_init, n_data_rates=8, aarf_n=8, log=False):
        self.SUPPORTED_DATA_RATES = n_data_rates
        assert 0 <= encoding_init < self.SUPPORTED_DATA_RATES, "Incorrect initial data rate"

        self.AARF_N = aarf_n
        self.idx = encoding_init
        self.log = log

        print "=================================="
        print "AARF algorithm is selected"
        print "No. of supporting data rates:", self.SUPPORTED_DATA_RATES
        print "Initial data rate index:", self.idx
        print "AARF_N:", self.AARF_N
        print "=================================="

        self.just_increased = False

        # idx | success | fails | threshold
        self.AARF_rate = [[0] * 4 for x in range(self.SUPPORTED_DATA_RATES)]  # [SUPPORTED_DATA_RATES]x4

        for i in range(self.SUPPORTED_DATA_RATES):
            self.AARF_rate[i][0] = i
            self.AARF_rate[i][3] = self.AARF_N

    def data_sel(self, rate, success):
        return self.aarf_update_stats(rate, success)

    def show_aarf_rate(self):
        if self.log:
            print "============== AARF_rate ==============="
            print_matrix(self.AARF_rate)
            print "========================================"

    def aarf_update_stats(self, rate, success):
        """
        success N times: increase, new self.idx first success then reset to N; fails decrease and N*2 fails twice:
        decrease
        :param rate:
        :param success:
        :return:
        """
        self.idx = rate
        # AARF_rate fields: [0] idx | [1] success | [2] fails | [3] threshold
        if success:
            self.AARF_rate[self.idx][2] = 0
            self.AARF_rate[self.idx][1] += 1

            if self.just_increased:  # Just increased to a new rate and first frame success
                self.just_increased = False
                return self.idx

            if self.AARF_rate[self.idx][1] == self.AARF_rate[self.idx][3]:  # Increase the data rate
                self.AARF_rate[self.idx][3] = self.AARF_N
                self.AARF_rate[self.idx][1] = 0
                self.just_increased = True

                return min(self.idx + 1, self.SUPPORTED_DATA_RATES - 1)

            return self.idx  # Unchange the current data rate

        # transmission fails
        self.AARF_rate[self.idx][1] = 0
        if self.just_increased:  # just increased to a new rate and first frame fails
            self.just_increased = False
            self.AARF_rate[self.idx - 1][3] *= 2  # Since just increased a new data rate, idx > 0
            if self.AARF_rate[self.idx - 1][3] > 20:
                self.AARF_rate[self.idx - 1][3] = 20

            return max(self.idx - 1, 0)

        if self.AARF_rate[self.idx][2] != 0:  # 2 frames fail
            self.AARF_rate[self.idx][2] = 0
            return max(self.idx - 1, 0)

        # first fail
        self.AARF_rate[self.idx][2] += 1
        return self.idx

    def test(self):
        d = 0  # initial data rate
        for i in range(20):
            d = self.data_sel(d, True)
            self.show_aarf_rate()
            print d

        d = self.data_sel(d, False)
        self.show_aarf_rate()
        print d

        for i in range(650):
            d = self.data_sel(d, False)
            self.show_aarf_rate()
            print d

        for i in range(300):
            d = self.data_sel(d, True)
            self.show_aarf_rate()
            print d

        d = self.data_sel(d, True)
        self.show_aarf_rate()
        print d


def print_matrix(m, log=True):
    if log:
        if type(m[0]) == int:  # x is a 1-D array
            print m
        elif type(m[0]) == list:  # x is a 2-D array
            for i in range(len(m)):
                print m[i]
        else:
            print "Not a 1-D or 2-D array"
