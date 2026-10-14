.PHONY: render lab baseline clean test collect destroy

render:
	python3 network-range/render.py network-range/variant.yml

lab: render
	mkdir -p evidence
	sudo containerlab deploy --topo topology.clab.yml

baseline:
	docker exec clab-netforge-a3-gateway nft -f /etc/nftables.conf

clean:
	-sudo containerlab destroy --topo topology.clab.yml --cleanup
	rm -f topology.clab.yml
	rm -rf configs/core/frr.conf configs/gateway/nftables.conf configs/gateway/bootstrap.sh
	rm -f test-results.xml

test:
	cd tests && python3 -m pytest -v --junitxml=../test-results.xml

collect:
	bash network-range/scripts/collect-state.sh evidence/reference-state

destroy:
	sudo containerlab destroy --topo topology.clab.yml --cleanup
