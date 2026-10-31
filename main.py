if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    import sys
    if '--check-discovery-worker'in sys.argv:
        from exile.reader_process import check_worker
        check_worker(sys.argv[sys.argv.index('--check-discovery-worker')+1])
    elif '--sharing-server' in sys.argv:
        from exile.sharing_server import main
        main(sys.argv[sys.argv.index('--sharing-server')+1:])
    elif '--check-routing-worker' in sys.argv:
        from exile.routing import check_worker
        check_worker(sys.argv[sys.argv.index('--check-routing-worker')+1])
    else:
        from exile.app import main
        main()
