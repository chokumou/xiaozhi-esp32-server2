import time
import random
from core.utils import dict_lookup


def bench_set_lookup(words, tests=100000):
    start = time.perf_counter()
    hits = 0
    for _ in range(tests):
        w = random.choice(words)
        if dict_lookup.contains(w):
            hits += 1
    end = time.perf_counter()
    return end - start, hits


def main():
    # load sample words from dict file
    base_words = list(dict_lookup._DICT_SET)[:300]
    if not base_words:
        print("No words loaded in dict; ensure core/data/japanese_top1000.txt exists")
        return
    t, h = bench_set_lookup(base_words, tests=100000)
    print(f"set lookup: {t:.3f}s for 100000 ops, hits={h}")


if __name__ == '__main__':
    main()



