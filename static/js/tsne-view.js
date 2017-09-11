/**
 * Created by benoit on 28/09/2016.
 */

angular.module('replicaModule')
    .directive('tsneView', function ($rootScope, $http) {
        function link(scope, el_base) {

            function getImageThumbnail(e) {
                return e.images[0].iiif_url + "/full/450,/0/default.jpg";
            }

            var el = el_base[0];
            var width = 800,
                height = 800;

            var nodes_data = null;

            var base_image_size = 40;
            var image_size = base_image_size;

            var zoom = d3.zoom()
                .scaleExtent([0.5, 20])
                .on("zoom", zoomed);

            var svg = d3.select(el).append("svg")
                .attr("width", '100%')
                .attr("height", height)
                .call(zoom);

            //svg.style("opacity", 1e-6)
            //    .transition()
            //    .duration(1000)
            //    .style("opacity", 1);

            var chart = svg
            //.attr("width", width)
            //.attr("height", height);
            //.attr("viewBox", "0 0 " + width + " " + height )
            //.attr("preserveAspectRatio", "xMinYMin")
                .append("g");

            function zoomed() {
                chart.attr("transform", d3.event.transform);
            }

            var centerx = d3.scaleLinear()
                        .range([0, width]);
            var centery = d3.scaleLinear()
                        .range([0, height]);
            var model = new tsnejs.tSNE({
                    dim: 2,
                    perplexity: 10,
                    epsilon: 3
                });

            var simulation = d3.forceSimulation()
                .force('tsne', function (alpha) {
                    // every time you call this, solution gets better
                    model.step();

                    // Y is an array of 2-D points that you can plot
                    var pos = model.getSolution();
                    if (pos && nodes_data) {

                        centerx.domain(d3.extent(pos.map(function (d) {
                            return d[0]
                        })));
                        centery.domain(d3.extent(pos.map(function (d) {
                            return d[1]
                        })));

                        nodes_data.forEach(function (d, i) {
                            if (!d.x) {
                                d.x = 0;
                            }
                            if (!d.y) {
                                d.y = 0;
                            }
                            d.x += alpha * (centerx(pos[i][0]) - d.x);
                            d.y += alpha * (centery(pos[i][1]) - d.y);
                        });
                    }
                    //console.log(model.iter);
                })
                .force('collide', d3.forceCollide().radius(function(d) {return image_size/2;}))
                .on("tick", ticked);


            var node_group = chart.append("g")
                .attr("class", "nodes");
            var node = node_group.selectAll(".node");

            function isInSelection(item, sel) {
                return !sel.every(function (e) {
                    return item.uid != e.uid
                });
            }

            function ticked() {
                node
                    .attr("transform", function (d) {
                        return "translate("+d.x+","+ d.y+")"
                    });
                node.selectAll("circle")
                    .attr("visibility", function(d) {
                        if (isInSelection(d, scope.selection))
                            return "visible";
                        else
                            return "hidden";
                    });
                node.selectAll(".cross")
                    .attr("visibility", function(d) {
                        if (isInSelection(d, scope.negativeSelection))
                            return "visible";
                        else
                            return "hidden";
                    });
            }

            scope.$watch('elements', function () {
                console.log(scope.elements.length);
                if (scope.elements.length == 0)
                    return;

                $http.post("/api/image/distance_matrix", {image_uids: scope.elements.map(function(d) {return d.images[0].uid})}).then(
                    function (response) {
                        model.initDataDist(response.data.distances);
                        model.iter=0;
                        nodes_data = scope.elements.slice(); // Duplicate
                        //image_size = base_image_size*150/(scope.elements.length+50);

                        // Apply the general update pattern to the nodes.
                        node = node_group.selectAll(".node");
                        node = node.data(nodes_data, function (d) {
                            return d.images[0].uid;
                        });
                        node.exit().remove();
                        node = node.enter()
                            .append("g")
                            .attr("class", "node")
                            .on("contextmenu", function (d, i) {
                                d3.event.preventDefault();
                                $rootScope.$broadcast('toggleNegativeSelection', d);
                            })
                            .on("click", function(d) {
                                $rootScope.$broadcast('toggleCurrentSelection', d);
                                //$rootScope.$broadcast('showImageDialog', d.images[0].uid)
                            })
                            .merge(node);
                        node
                            .append("image")
                            .attr("xlink:href", function (d) {
                                return getImageThumbnail(d);
                            })
                            .attr("x", -image_size/2)
                            .attr("y", -image_size/2)
                            .attr("width", image_size)
                            .attr("height", image_size);

                        node.append("circle")
                            .attr("r", image_size/2);
                        crosses = node.append("g")
                            .attr("class", 'cross');
                        crosses.append('line')
                            .attr("x1", -image_size/2)
                            .attr("y1", -image_size/2)
                            .attr("x2", +image_size/2)
                            .attr("y2", +image_size/2);
                        crosses.append('line')
                            .attr("x1", +image_size/2)
                            .attr("y1", -image_size/2)
                            .attr("x2", -image_size/2)
                            .attr("y2", +image_size/2);
                        // Update and restart the simulation.
                        simulation.nodes(nodes_data);
                        simulation.alphaDecay(0.0001)
                            .alpha(0.02).restart();
                        // Zoom re-initialization
                        svg.call(zoom.transform, d3.zoomIdentity);
                    }, function (response) {
                        scope.showErrorToast("Search failed", response);
                    }
                );

            });

            scope.$on('$destroy', function() {
                console.log("destroy");
                simulation.stop();
              });

        }

        return {
            link: link,
            restrict: 'E',
            scope: {selection: '=', negativeSelection: '=', elements: '='},
            controller: function($scope) {

            }
        }
    });