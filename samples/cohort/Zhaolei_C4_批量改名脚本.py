#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量改名脚本 — C4 test fixture (synthetic, by Zhaolei).

故意保留硬编码绝对路径，用来验证评审器能抓到「不可复用」。
"""

import os

SOURCE = "D:\\我的资料\\课件"
TARGET = "D:\\我的资料\\改名结果"
PREFIX = "2026秋-"


def rename_all():
    os.makedirs(TARGET, exist_ok=True)
    for index, name in enumerate(os.listdir(SOURCE), 1):
        source = os.path.join(SOURCE, name)
        target = os.path.join(TARGET, "%s%02d-%s" % (PREFIX, index, name))
        os.rename(source, target)
        print("renamed:", target)


if __name__ == "__main__":
    rename_all()
