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
    # 사용법: python src/recaman.py [개수] [저장할 파일]   (기본 20개, 화면 출력)
    #   예) python src/recaman.py 1000000 recaman.txt   -> 한 줄에 한 항씩 파일로 저장
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    out_path = sys.argv[2] if len(sys.argv) > 2 else None

    seq = recaman(n)

    print("=" * 60)
    print(f" 레카만 수열 - 처음 {n}개 항")
    print("=" * 60)

    if out_path:
        with open(out_path, "w") as f:
            f.write("\n".join(str(x) for x in seq) + "\n")
        print(f"-> {out_path} 에 저장 완료")
        if seq:
            print(f"-> 마지막 항: {seq[-1]}, 가장 큰 값: {max(seq)}")
    else:
        print(", ".join(str(x) for x in seq))


if __name__ == "__main__":
    main()
