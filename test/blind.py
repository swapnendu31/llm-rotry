a = [1,2,3]

def add(x, *y):
    print(x, *y)


if __name__ == "__main__":
    print(*a)