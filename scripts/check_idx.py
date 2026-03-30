from src.pipeline.data_connectors.idx_listings import get_idx_count, get_idx_listings


def main():
    try:
        cnt = get_idx_count()
        print('IDX count:', cnt)
        # show a few entries if available
        try:
            items = get_idx_listings()
            print('Example entries (first 5):')
            for it in items[:5]:
                print(it)
        except Exception:
            pass
    except Exception as e:
        print('Error fetching IDX listings:', repr(e))

if __name__ == '__main__':
    main()
