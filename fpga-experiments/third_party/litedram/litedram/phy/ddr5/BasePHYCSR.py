#
# This file is part of LiteDRAM.
#
# Copyright (c) 2022 Antmicro <www.antmicro.com>
# SPDX-License-Identifier: BSD-2-Clause


from migen.fhdl.module import Module
from litex.soc.interconnect.csr import AutoCSR, CSR, CSRStorage, CSRField, CSRStatus


class BasePHYCSR(Module, AutoCSR):
    def __init__(self, prefixes, nphases, nranks, nibbles,
                 with_clock_odelay, with_address_odelay,
                 with_idelay, with_odelay,
                 with_per_dq_idelay, databits, dq_dqs_ratio):
        self._enable_fifos = CSRStorage(reset=0)
        self._rst          = CSRStorage(reset=1)

        self._rdimm_mode   = CSRStorage()
        self._rdimm_mode.storage.attr.add("slow_ff")
        self._rdimm_mode.storage.attr.add("keep")

        self._rdphase = CSRStorage(nphases.bit_length()-1, reset=0)
        self._wrphase = CSRStorage(nphases.bit_length()-1, reset=0)

        self.alert = CSRStatus(1)
        self.alert_reduce = CSRStorage(fields=[
            CSRField("initial_state", size=1,  description="Initial value of all bits"),
            CSRField("operation",     size=1,  description="0 - `or` (default), 1 -`and`"),
        ])
        self.sample_alert = CSRStorage()
        self.reset_alert = CSR()

        if with_odelay or with_clock_odelay:
            setattr(self, 'ckdly_rst' , CSR(name='ckdly_rst'))
            setattr(self, 'ckdly_inc' , CSR(name='ckdly_inc'))

        for prefix in prefixes:
            setattr(self, prefix+'preamble', CSRStatus(2*2, name=prefix+'preamble'))
            getattr(self, prefix+'preamble').status.attr.add("slow_in")
            getattr(self, prefix+'preamble').status.attr.add("keep")

            setattr(self, prefix+'wlevel_en', CSRStorage(name=prefix+'wlevel_en'))
            getattr(self, prefix+'wlevel_en').storage.attr.add("slow_ff")
            getattr(self, prefix+'wlevel_en').storage.attr.add("keep")

            setattr(self, prefix+'par_enable', CSRStorage(name=prefix+'par_enable', reset=0))
            getattr(self, prefix+'par_enable').storage.attr.add("slow_ff")
            getattr(self, prefix+'par_enable').storage.attr.add("keep")

            setattr(self, prefix+'par_value', CSRStorage(name=prefix+'par_value', reset=0))
            getattr(self, prefix+'par_value').storage.attr.add("slow_ff")
            getattr(self, prefix+'par_value').storage.attr.add("keep")

            setattr(self, prefix+'discard_rd_fifo', CSRStorage(name=prefix+'discard_rd_fifo'))
            getattr(self, prefix+'discard_rd_fifo').storage.attr.add("slow_ff")
            getattr(self, prefix+'discard_rd_fifo').storage.attr.add("keep")

            setattr(self, prefix+'dly_sel', CSRStorage(
                max(14, nranks, nibbles), name=prefix+'dly_sel'))
            getattr(self, prefix+'dly_sel').storage.attr.add("slow_ff")
            getattr(self, prefix+'dly_sel').storage.attr.add("keep")

            if nibbles%2 == 0:
                setattr(self, prefix+'dq_dqs_ratio',
                    CSRStorage(4, name=prefix+'dq_dqs_ratio', reset=dq_dqs_ratio))
                getattr(self, prefix+'dq_dqs_ratio').storage.attr.add("slow_ff")
                getattr(self, prefix+'dq_dqs_ratio').storage.attr.add("keep")

            setattr(self, prefix+'ck_rdly_inc', CSR(name=prefix+'ck_rdly_inc'))
            setattr(self, prefix+'ck_rdly_rst', CSR(name=prefix+'ck_rdly_rst'))
            setattr(self, prefix+'ck_rddly_dq', CSRStatus(16, name=prefix+'ck_rddly'))
            getattr(self, prefix+'ck_rddly_dq').status.attr.add("slow_in")
            getattr(self, prefix+'ck_rddly_dq').status.attr.add("keep")
            setattr(self, prefix+'ck_rddly_preamble', CSRStatus(16, name=prefix+'ck_rddly_preamble'))
            getattr(self, prefix+'ck_rddly_preamble').status.attr.add("slow_in")
            getattr(self, prefix+'ck_rddly_preamble').status.attr.add("keep")

            setattr(self, prefix+'ck_wdly_inc', CSR(name=prefix+'ck_wdly_inc'))
            setattr(self, prefix+'ck_wdly_rst', CSR(name=prefix+'ck_wdly_rst'))
            setattr(self, prefix+'ck_wdly_dqs', CSRStatus(16, name=prefix+'ck_wdly_dqs'))
            getattr(self, prefix+'ck_wdly_dqs').status.attr.add("slow_in")
            getattr(self, prefix+'ck_wdly_dqs').status.attr.add("keep")
            setattr(self, prefix+'ck_wddly_inc', CSR(name=prefix+'ck_wddly_inc'))
            setattr(self, prefix+'ck_wddly_rst', CSR(name=prefix+'ck_wddly_rst'))
            setattr(self, prefix+'ck_wdly_dq', CSRStatus(16, name=prefix+'ck_wdly_dq'))
            getattr(self, prefix+'ck_wdly_dq').status.attr.add("slow_in")
            getattr(self, prefix+'ck_wdly_dq').status.attr.add("keep")

            if with_per_dq_idelay :
                setattr(self, prefix+'dq_dly_sel', CSRStorage(dq_dqs_ratio, name=prefix+'dq_dly_sel'))
                getattr(self, prefix+'dq_dly_sel').storage.attr.add("slow_ff")
                getattr(self, prefix+'dq_dly_sel').storage.attr.add("keep")

            if with_odelay or with_address_odelay:
                setattr(self, prefix+'csdly_rst',  CSR(name=prefix+'csdly_rst'))
                setattr(self, prefix+'csdly_inc',  CSR(name=prefix+'csdly_inc'))
                setattr(self, prefix+'cadly_rst',  CSR(name=prefix+'cadly_rst'))
                setattr(self, prefix+'cadly_inc',  CSR(name=prefix+'cadly_inc'))
                setattr(self, prefix+'pardly_rst', CSR(name=prefix+'pardly_rst'))
                setattr(self, prefix+'pardly_inc', CSR(name=prefix+'pardly_inc'))

                setattr(self, prefix+'csdly', CSRStatus(16, name=prefix+'csdly'))
                getattr(self, prefix+'csdly').status.attr.add("slow_in")
                getattr(self, prefix+'csdly').status.attr.add("keep")

                setattr(self, prefix+'cadly', CSRStatus(16, name=prefix+'cadly'))
                getattr(self, prefix+'cadly').status.attr.add("slow_in")
                getattr(self, prefix+'cadly').status.attr.add("keep")

            if with_idelay:
                setattr(self, prefix+'rdly_dq_rst',  CSR(name=prefix+'rdly_dq_rst'))
                setattr(self, prefix+'rdly_dq_inc',  CSR(name=prefix+'rdly_dq_inc'))
                setattr(self, prefix+'rdly_dqs_rst', CSR(name=prefix+'rdly_dqs_rst'))
                setattr(self, prefix+'rdly_dqs_inc', CSR(name=prefix+'rdly_dqs_inc'))

                setattr(self, prefix+'rdly_dqs', CSRStatus(16, name=prefix+'rdly_dqs'))
                getattr(self, prefix+'rdly_dqs').status.attr.add("slow_in")
                getattr(self, prefix+'rdly_dqs').status.attr.add("keep")
                setattr(self, prefix+'rdly_dq', CSRStatus(16, name=prefix+'rdly_dq'))
                getattr(self, prefix+'rdly_dq').status.attr.add("slow_in")
                getattr(self, prefix+'rdly_dq').status.attr.add("keep")

            if with_odelay:
                setattr(self, prefix+'wdly_dq_rst',  CSR(name=prefix+'wdly_dq_rst'))
                setattr(self, prefix+'wdly_dq_inc',  CSR(name=prefix+'wdly_dq_inc'))
                setattr(self, prefix+'wdly_dm_rst',  CSR(name=prefix+'wdly_dm_rst'))
                setattr(self, prefix+'wdly_dm_inc',  CSR(name=prefix+'wdly_dm_inc'))
                setattr(self, prefix+'wdly_dqs_rst', CSR(name=prefix+'wdly_dqs_rst'))
                setattr(self, prefix+'wdly_dqs_inc', CSR(name=prefix+'wdly_dqs_inc'))

                setattr(self, prefix+'wdly_dqs', CSRStatus(16, name=prefix+'wdly_dqs'))
                getattr(self, prefix+'wdly_dqs').status.attr.add("slow_in")
                getattr(self, prefix+'wdly_dqs').status.attr.add("keep")
                setattr(self, prefix+'wdly_dq', CSRStatus(16, name=prefix+'wdly_dq'))
                getattr(self, prefix+'wdly_dq').status.attr.add("slow_in")
                getattr(self, prefix+'wdly_dq').status.attr.add("keep")
                setattr(self, prefix+'wdly_dm', CSRStatus(16, name=prefix+'wdly_dm'))
                getattr(self, prefix+'wdly_dm').status.attr.add("slow_in")
                getattr(self, prefix+'wdly_dm').status.attr.add("keep")

    def CSR_to_dict(self):
        return {key: value for key, value in self.__dict__.items()}
