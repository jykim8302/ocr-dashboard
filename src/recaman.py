import sys


def recaman(n):
    """레카만 수열의 처음 n개 항을 리스트로 돌려줍니다.

    규칙
      a(0) = 0
      a(k) = a(k-1) - k   (결과가 0 이상이고, 아직 안 나온 수일 때)
      a(k) = a(k-1) + k   (그 밖의 경우)
    """
    seq = []
    seen = set()
    for k in range(n):
        if k == 0:
            value = 0
        else:
            prev = seq[-1]
            value = prev - k
            if value < 0 or value in seen:
                value = prev + k
        seq.append(value)
        seen.add(value)
    return seq


def main():
    # 사용법: python src/recaman.py [개수]   (기본 20개)
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20

    print("=" * 60)
    print(f" 레카만 수열 - 처음 {n}개 항")
    print("=" * 60)
    print(", ".join(str(x) for x in recaman(n)))


if __name__ == "__main__":
    main()
